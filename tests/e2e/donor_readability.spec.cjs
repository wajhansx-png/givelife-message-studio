const {test,expect}=require('@playwright/test');

// Uses the isolated fake app backend. No WhatsApp messages are sent.
for (const [width,height,expected] of [[1440,900,'17px'],[390,844,'16px']]) {
 test('Donor Messages uses stable eye-comfort typography '+width,async({page})=>{
  await page.setViewportSize({width,height});
  await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
  await page.goto('/#/donors/messages');
  const preview=page.locator('.bank-detail .bank-preview');
  await expect(preview).toBeVisible();
  await expect(preview).toHaveCSS('font-size',expected);
  await expect(preview).toHaveCSS('line-height',width>=900?'25.5px':'24px');
  const before=await preview.evaluate(el=>getComputedStyle(el).fontSize);
  await page.setViewportSize({width:width+12,height:height-80});
  await expect(preview).toHaveCSS('font-size',expected);
  const after=await preview.evaluate(el=>getComputedStyle(el).fontSize);
  expect(after).toBe(before);
  expect(await preview.evaluate(el=>el.style.fontSize)).toBe('');
  await page.locator('.bank-actions [data-bank-save-id]').click();
  const edit=page.locator('.bank-detail textarea');
  await expect(edit).toBeVisible();
  await expect(edit).toHaveCSS('font-size',expected);
 });
}
