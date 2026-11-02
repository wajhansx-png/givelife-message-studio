const {test,expect}=require('@playwright/test');
for(const width of [1440,390])test('Donor Messages uses focused black Group-style editor '+width,async({page})=>{
 await page.setViewportSize({width,height:900});
 await page.addInitScript(()=>localStorage.setItem('givelife-cloud-key','manual-fix-preview-key'));
 await page.goto('/#/donors/messages');
 await expect(page.locator('#donorsPage')).toBeVisible();
 await expect(page.locator('#donorsPage')).toHaveAttribute('data-panel','messages');
 await expect(page.locator('.bank-workspace')).toBeVisible();
 await expect(page.locator('.bank-message.bank-detail')).toBeVisible();
 await expect(page.locator('.bank-actions')).toBeVisible();
 await expect(page.locator('.bank-picker')).toBeVisible();
 await expect(page.locator('.bank-picker [data-bank-id]').first()).toBeVisible();
 await expect(page.locator('#donorMessages')).toHaveCSS('background-color','rgb(35, 35, 35)');
 const editor=page.locator('.bank-detail textarea');
 await page.locator('.bank-actions [data-bank-save-id]').click();
 await expect(editor).toBeVisible();
 await expect(page.locator('.bank-actions [data-bank-save-id]')).toHaveText('Save');
 // This is only a UI test: never click Send or submit an edited fundraising caption.
});
