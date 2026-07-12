const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1080, height: 1080 });
  await page.goto('file:///C:/Users/nai19/Documents/GitHub/ianrosado.com/instagram/plan_your_weekend_jun25_28.html');
  await page.waitForTimeout(1500);
  const el = await page.$('.post');
  await el.screenshot({ path: 'C:/Users/nai19/Documents/GitHub/ianrosado.com/instagram/plan_your_weekend_jun25_28.png', deviceScaleFactor: 2 });
  await browser.close();
  console.log('wrote plan_your_weekend_jun25_28.png');
})();
