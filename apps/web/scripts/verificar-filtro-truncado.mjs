/** Verifica que el filtro acepta codigos pegados truncados (sin el ultimo caracter). */
import { chromium } from "@playwright/test";

const URL = process.env.VERCEL_URL ?? "https://olataforma-sugerencias-web.vercel.app";
const EMAIL = process.env.LOGIN_EMAIL ?? "fmora@curifor.com";
const PASS = process.env.LOGIN_PASSWORD ?? "123456";

// Codigos truncados (como los muestra el BI con la columna estrecha)
const PEGADO = "19 HL3Z8005\n25 MB3Z2001\n19 ER3Z6584";

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
    await page.waitForSelector(".ag-row", { timeout: 90000 });
    await page.waitForTimeout(1500);

    console.log("2. Abrir filtro de Producto");
    const headerProducto = page.locator(".ag-header-cell[col-id='producto']").first();
    await headerProducto.locator(".ag-header-icon").first().click();
    await page.waitForSelector('input[placeholder*="Buscar en Producto"]', { timeout: 10000 });

    // Cuantos checkboxes hay en el popup ANTES de pegar (debe ser ~500 si allValues OK)
    const checkboxesAntes = await page.$$eval(
      "label .truncate",
      (els) => els.length
    );
    console.log("   Checkboxes en popup ANTES de pegar:", checkboxesAntes);

    console.log("3. Pegar codigos TRUNCADOS:", JSON.stringify(PEGADO));
    await page.evaluate(async (text) => {
      const input = document.querySelector('input[placeholder*="Buscar en Producto"]');
      input.focus();
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      input.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true }));
    }, PEGADO);

    await page.waitForSelector("text=Lista pegada", { timeout: 5000 });

    // Leer el marcador de debug
    const debug = await page.evaluate(() => window.__filtroDebug);
    console.log("   Debug:", JSON.stringify(debug));

    // Leer el feedback de cuantos exactos / expandidos / sin match
    const feedback = await page.locator("text=/pegado/").nth(1).textContent().catch(() => "");
    console.log("   Feedback:", feedback);

    // Leer los valores que quedaron en la lista pegada (los matches reales)
    const matchedValues = await page.$$eval(
      ".ag-popup label .truncate, body label.flex .truncate",
      (els) => els.map((e) => e.textContent?.trim() ?? "").filter(Boolean)
    );
    console.log("   Valores matched:", matchedValues);

    console.log("4. ACEPTAR");
    await page.click('button:has-text("ACEPTAR")');
    await page.waitForTimeout(1500);

    const popupVisible = await page.isVisible('input[placeholder*="Buscar en Producto"]');
    console.log("   Popup cerrado?", !popupVisible);

    const productosFiltrados = await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.map((c) => c.textContent?.trim() ?? "")
    );
    const unicos = [...new Set(productosFiltrados)];
    console.log("5. Productos UNICOS visibles tras filtrar:", unicos);

    // Esperamos que todos empiecen con uno de los 3 prefijos pegados
    const prefijos = ["19 HL3Z8005", "25 MB3Z2001", "19 ER3Z6584"];
    const indeseados = unicos.filter((p) => !prefijos.some((pr) => p.startsWith(pr)));
    console.log("\n=== RESULTADO ===");
    console.log("Unicos con prefijo esperado:", unicos.length - indeseados.length, "/", unicos.length);
    console.log("Indeseados:", indeseados);

    if (!popupVisible && indeseados.length === 0 && unicos.length > 0) {
      console.log("\nFILTRO PREFIJO OK");
      process.exit(0);
    } else {
      console.log("\nFILTRO PREFIJO FALLA");
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
