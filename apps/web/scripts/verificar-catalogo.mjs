/** Verifica end-to-end:
 * 1. Pagina /catalogo carga y muestra productos.
 * 2. En el dashboard, al buscar un codigo que NO esta en el sugerido,
 *    aparece la fila del catalogo con badge.
 */
import { chromium } from "@playwright/test";

const URL = process.env.VERCEL_URL ?? "https://olataforma-sugerencias-web.vercel.app";
const EMAIL = process.env.LOGIN_EMAIL ?? "fmora@curifor.com";
const PASS = process.env.LOGIN_PASSWORD ?? "123456";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log("[page error]", e.message));

  try {
    console.log("1. Login");
    await page.goto(URL, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForTimeout(2000);
    if (page.url().includes("/login")) {
      await page.fill('input[type="email"]', EMAIL);
      await page.fill('input[type="password"]', PASS);
      await page.locator('button[type="submit"], button:has-text("Entrar")').first().click();
      await page.waitForURL((u) => !u.toString().includes("/login"), { timeout: 60000 });
    }

    // --- Test 1: pagina /catalogo ---
    console.log("\n=== Test 1: pagina /catalogo ===");
    await page.goto(`${URL}/catalogo`, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForSelector(".ag-row", { timeout: 60000 });
    await page.waitForTimeout(1500);

    const productosCat = await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.slice(0, 5).map((c) => c.textContent?.trim() ?? "")
    );
    console.log("   Primeros 5 productos en catalogo:", productosCat);

    // Leer el contador en el header
    const headerText = await page.locator("p.text-\\[13px\\]").first().textContent();
    console.log("   Header:", headerText);

    const test1OK = productosCat.length === 5 && headerText?.includes("productos");

    // --- Test 2: busqueda en dashboard incluye catalogo ---
    console.log("\n=== Test 2: dashboard busca tambien en catalogo ===");
    await page.goto(URL, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForSelector(".ag-row", { timeout: 60000 });
    await page.waitForTimeout(1500);

    // Buscar un producto que probablemente no este en sugerido (algo random del catalogo)
    // Usamos uno generico como "CAJA CARTON" (es un producto-no-comercial del catalogo)
    const busqueda = "CAJA CARTON";
    console.log("   Buscando:", busqueda);
    // Esperar a que la respuesta del nuevo q llegue antes de inspeccionar la grilla.
    const resp = page.waitForResponse(
      (r) => r.url().includes("/api/sugerido?") && r.url().includes("q=CAJA"),
      { timeout: 30000 }
    );
    await page.fill('input[placeholder*="Buscar producto"]', busqueda);
    const r = await resp;
    console.log("   API status:", r.status());
    try {
      const j = await r.json();
      console.log("   API total:", j.total, "items:", j.items?.length);
    } catch {}
    await page.waitForTimeout(1500); // que AG Grid pinte

    // Contar filas y ver si hay badge CATALOGO
    const filasInfo = await page.$$eval(
      ".ag-row",
      (rows) => rows.map((r) => {
        const prod = r.querySelector(".ag-cell[col-id='producto']");
        return {
          producto: prod?.textContent?.trim().replace("CATÁLOGO", "").trim() ?? "",
          tieneBadge: prod?.innerHTML.includes("CATÁLOGO") ?? false,
        };
      })
    );
    const conBadge = filasInfo.filter((r) => r.tieneBadge);
    console.log("   Total filas visibles:", filasInfo.length);
    console.log("   Filas con badge CATALOGO:", conBadge.length);
    if (conBadge.length > 0) {
      console.log("   Primeras 3 con badge:", conBadge.slice(0, 3).map((r) => r.producto));
    }

    const test2OK = conBadge.length > 0;

    console.log("\n=== RESULTADO ===");
    console.log("Test 1 (pagina catalogo):", test1OK ? "OK" : "FALLA");
    console.log("Test 2 (busqueda mixta en dashboard):", test2OK ? "OK" : "FALLA");

    if (test1OK && test2OK) {
      console.log("\nCATALOGO OK");
      process.exit(0);
    } else {
      console.log("\nCATALOGO FALLA");
      process.exit(2);
    }
  } catch (e) {
    console.error("ERROR:", e.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
