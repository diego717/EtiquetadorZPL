import json
import shutil
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SALES_SCRIPT_PATHS = (
    PROJECT_ROOT / "googleScripts" / "06_VentasNeo.txt",
    PROJECT_ROOT
    / "googleScripts_migracion_libreria"
    / "library_src"
    / "06_VentasNeo.gs",
    PROJECT_ROOT
    / "googleScripts_webapp_full_migration"
    / "server_src"
    / "06_VentasNeo.gs",
)


def _extract_javascript_function(source: str, function_name: str) -> str:
    marker = f"function {function_name}("
    start = source.index(marker)
    opening_brace = source.index("{", start)
    depth = 0

    for index in range(opening_brace, len(source)):
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]

    raise AssertionError(f"La funcion {function_name} no tiene cierre")


class SalesKitFilterTests(unittest.TestCase):
    def test_sales_sync_property_names_have_backward_compatible_fallbacks(self):
        for path in SALES_SCRIPT_PATHS:
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8")
                self.assertIn(
                    'return configuredName || "ODOO_SALES_LAST_SYNC_UTC";',
                    source,
                )
                self.assertIn(
                    'return configuredName || "ODOO_SALES_LINE_LAST_SYNC_UTC";',
                    source,
                )
                self.assertNotIn(
                    "properties.setProperty(SALES_CFG.LINE_LAST_SYNC_PROPERTY",
                    source,
                )

    def test_primary_sales_script_has_pending_sort_compatibility_fallback(self):
        source = SALES_SCRIPT_PATHS[0].read_text(encoding="utf-8")
        self.assertIn("function consumeSalesPendingAutoSort_()", source)
        self.assertIn('const propertyName = "PENDING_AUTO_SORT";', source)
        self.assertIn("if (consumeSalesPendingAutoSort_())", source)

    def test_primary_sales_script_supports_older_utilities_file(self):
        source = SALES_SCRIPT_PATHS[0].read_text(encoding="utf-8")
        compatibility_helper = _extract_javascript_function(
            source, "resetSalesOperationalRowFontColor_"
        )

        self.assertIn(
            'typeof resetOperationalRowFontColor_ === "function"',
            compatibility_helper,
        )
        self.assertIn('sheet.getRange(row, 4, 1, 5).setFontColor', compatibility_helper)
        self.assertEqual(
            source.count("resetSalesOperationalRowFontColor_(sheet,"),
            4,
            "Debe existir el helper y cubrir limpieza, sincronizacion e importacion manual",
        )

    def test_all_sales_script_copies_filter_kits_in_both_read_paths(self):
        source = SALES_SCRIPT_PATHS[0].read_text(encoding="utf-8")
        self.assertIn("function fetchKitDefinitionsByLines_", source)
        self.assertIn("function buildSaleOrderProductLines_", source)
        self.assertIn('["type", "=", "phantom"]', source)
        self.assertIn('["type", "=", "normal"]', source)
        self.assertIn('"mrp.bom.line"', source)

    @unittest.skipUnless(shutil.which("node"), "Node.js no esta disponible")
    def test_kit_detection_handles_template_and_variant_boms(self):
        source = SALES_SCRIPT_PATHS[0].read_text(encoding="utf-8")
        chunk_function = _extract_javascript_function(source, "chunkValues_")
        definitions_function = _extract_javascript_function(
            source, "fetchKitDefinitionsByLines_"
        )
        build_function = _extract_javascript_function(
            source, "buildSaleOrderProductLines_"
        )
        harness = f"""
{chunk_function}
{definitions_function}
{build_function}

function getMany2oneId_(value) {{
  if (Array.isArray(value)) return String(value[0] || "");
  return "";
}}

function cleanString_(value) {{ return value === null || value === undefined ? "" : String(value); }}
function normalizeQuantity_(value) {{
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}}
function isSaleOrderLineForProduction_(_line) {{ return true; }}
function extractProductDescription_(value) {{ return String(value || ""); }}
function extractProductCode_(_line, _productCodeMap) {{ return ""; }}
function logDebug_(_message) {{}}
function getMany2oneName_(value) {{ return Array.isArray(value) ? String(value[1] || "") : ""; }}
function fetchProductCodesByLines_(_cfg, _uid, _lines) {{ return new Map(); }}

const templatesByProduct = new Map([
  [101, 10],
  [102, 10],
  [201, 20],
  [301, 30],
  [401, 40],
]);

function executeKw_(_cfg, _uid, model, method, args, _kwargs) {{
  if (method !== "search_read") throw new Error("Metodo inesperado");

  if (model === "product.product") {{
    const ids = args[0][0][2];
    return ids.map((id) => templatesByProduct.has(id)
      ? {{ id, product_tmpl_id: [templatesByProduct.get(id), `Template ${{id}}`] }}
      : {{ id, product_tmpl_id: [id === 501 ? 50 : 60, `Component ${{id}}`], default_code: id === 501 ? "CARD" : "RIBBON", display_name: id === 501 ? "Tarjeta preimpresa" : "Ribbon" }});
  }}

  if (model === "mrp.bom.line") {{
    return [
      {{ id: 900, bom_id: [1, "Kit"], product_id: [501, "Tarjeta preimpresa"], product_qty: 400 }},
      {{ id: 901, bom_id: [1, "Kit"], product_id: [502, "Ribbon"], product_qty: 1 }},
    ];
  }}

  if (model === "mrp.bom") {{
    const domain = args[0];
    const type = domain.find((condition) => condition[0] === "type")[2];
    if (type === "phantom") return [{{ id: 1, product_id: false, product_tmpl_id: [10, "T10"], product_qty: 1 }}];
    return [{{ id: 5, product_id: [501, "Tarjeta"], product_tmpl_id: [50, "T50"] }}];
  }}

  throw new Error(`Modelo inesperado: ${{model}}`);
}}

const lines = [{{
  id: 120240,
  order_id: [58670, "S58670"],
  product_id: [101, "KIT 400"],
  product_uom_qty: 1,
  customer_lead: 0,
  name: "KIT 400",
}}];
const result = buildSaleOrderProductLines_({{}}, 1, lines);
process.stdout.write(JSON.stringify(result));
"""

        completed = subprocess.run(
            [shutil.which("node"), "-e", harness],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            json.loads(completed.stdout),
            [{
                "orderId": "58670",
                "code": "CARD",
                "description": "Tarjeta preimpresa",
                "quantity": 400,
                "isKitComponent": True,
                "lineId": "120240:kit:900",
            }],
        )


if __name__ == "__main__":
    unittest.main()
