// サムネ作成ページを開いて、案ごとのサムネをJPGで保存する(python -m material_collector.thumbnail ... --render から呼ばれる)
// 使い方: node render_thumbnails.js <ページのHTML> <保存先フォルダ> <名前>
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
(async () => {
  const [page, outDir, name] = process.argv.slice(2);
  const browser = await chromium.launch();
  const tab = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  tab.on("pageerror", e => console.error("ページのエラー:", e.message));
  await tab.goto("file://" + page);
  await tab.waitForFunction(() => typeof plans !== "undefined" && plans.length && (DATA.photos.every((_, i) => !DATA.embedded[i + 1] || photos.has(i + 1))), null, { timeout: 30000 });
  await tab.waitForTimeout(1500);  // 文字の形(Webフォント)と描き直しを待つ
  const shots = await tab.evaluate(() => plans.map((p, i) => ({ title: DATA.plans[i].title, url: p.canvas.toDataURL("image/jpeg", 0.92) })));
  for (const s of shots) {
    const file = path.join(outDir, `${name}_サムネ_${s.title}.jpg`);
    fs.writeFileSync(file, Buffer.from(s.url.split(",")[1], "base64"));
    console.log("保存しました:", file);
  }
  await browser.close();
})();
