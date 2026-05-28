/**
 * Verifica el filtro multi-select directamente contra produccion.
 *
 * Uso: node scripts/verificar-filtro.mjs
 * Variables: VERCEL_URL (def. la prod) - LOGIN_EMAIL - LOGIN_PASSWORD
 */
import { chromium } from "@playwright/test";

const URL = process.env.VERCEL_URL ?? "https://olataforma-sugerencias-web.vercel.app";
const EMAIL = process.env.LOGIN_EMAIL ?? "fmora@curifor.com";
const PASS = process.env.LOGIN_PASSWORD ?? "123456";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  // Log de errores de consola del navegador
  page.on("pageerror", (e) => console.log("[page error]", e.message));
  page.on("console", (m) => {
    if (m.type() === "error") console.log("[console error]", m.text());
  });

  try {
    console.log("1. Abriendo", URL);
    await page.goto(URL, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForTimeout(2000); // dar tiempo al redirect client-side

    console.log("   URL final:", page.url());

    // Esperar el form de login O la tabla
    const loginInput = page.locator('input[type="email"]').first();
    const tabla = page.locator(".ag-row").first();
    await Promise.race([
      loginInput.waitFor({ timeout: 30000 }).catch(() => null),
      tabla.waitFor({ timeout: 30000 }).catch(() => null),
    ]);

    if (await loginInput.isVisible().catch(() => false)) {
      console.log("2. Login con", EMAIL);
      await page.fill('input[type="email"]', EMAIL);
      await page.fill('input[type="password"]', PASS);
      // El boton puede decir "Entrar" o "Iniciar sesion"
      const submitBtn = page.locator('button[type="submit"], button:has-text("Entrar"), button:has-text("Iniciar")').first();
      await submitBtn.click();
      await page.waitForURL((u) => !u.toString().includes("/login"), { timeout: 60000 });
    }

    console.log("3. Esperando la tabla del Dashboard…");
    await page.waitForSelector(".ag-row", { timeout: 90000 });
    await page.waitForTimeout(1500); // dejar que la tabla termine de poblar

    // Capturar 3 productos DISTINTOS visibles
    const todos = await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.map((c) => c.textContent?.trim() ?? "")
    );
    const productosIniciales = [];
    const setP = new Set();
    for (const p of todos) {
      if (p && !setP.has(p)) { setP.add(p); productosIniciales.push(p); }
      if (productosIniciales.length === 3) break;
    }
    console.log("   Productos iniciales (3 distintos):", productosIniciales);
    if (productosIniciales.length < 3) throw new Error("No hay suficientes filas únicas");

    // Abrir filtro de Producto
    console.log("4. Abriendo filtro de Producto…");
    const headerProducto = page.locator(".ag-header-cell[col-id='producto']").first();
    await headerProducto.locator(".ag-header-icon").first().click();
    await page.waitForSelector('input[placeholder*="Buscar en Producto"]', { timeout: 10000 });

    // Pegar lista
    const listaPegada = productosIniciales.join("\n");
    console.log("5. Pegando lista:", JSON.stringify(listaPegada));
    await page.evaluate(async (text) => {
      const input = document.querySelector(
        'input[placeholder*="Buscar en Producto"]'
      );
      input.focus();
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      input.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true }));
    }, listaPegada);

    await page.waitForSelector("text=Lista pegada", { timeout: 5000 });
    console.log("   Aviso de lista pegada visible OK");
    await page.screenshot({ path: "scripts/filtro-pre.png" });

    // Click ACEPTAR
    console.log("6. Click ACEPTAR…");
    await page.click('button:has-text("ACEPTAR")');
    await page.waitForTimeout(1500);

    const popupVisible = await page.isVisible('input[placeholder*="Buscar en Producto"]');
    console.log("   Popup sigue visible?", popupVisible);
    await page.screenshot({ path: "scripts/filtro-post.png" });

    // Productos visibles tras filtrar
    const productosFiltrados = await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.map((c) => c.textContent?.trim() ?? "")
    );
    console.log("7. Productos visibles tras filtrar:", productosFiltrados);

    const setPegados = new Set(productosIniciales);
    const indeseados = productosFiltrados.filter((p) => !setPegados.has(p));
    const faltantes = productosIniciales.filter((p) => !productosFiltrados.includes(p));

    console.log("\n=== RESULTADO ===");
    console.log("Indeseados:", indeseados.length, indeseados.slice(0, 5));
    console.log("Faltantes:", faltantes.length, faltantes);
    console.log("Popup cerrado?", !popupVisible);

    if (indeseados.length === 0 && popupVisible === false) {
      console.log("\nFILTRO OK");
      process.exit(0);
    } else {
      console.log("\nFILTRO FALLA");
      process.exit(2);
    }
  } catch (e) {
    console.error("ERROR:", e.message);
    await page.screenshot({ path: "scripts/filtro-error.png" }).catch(() => {});
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
