const {test,expect}=require('@playwright/test');
// The Team launcher is intentionally removed from the navigation (compact-nav.js drops #openTeam), so the
// Team screen has no entry point. Re-enable these tests when Team is reachable again.
test.skip(true,'Team has no navigation entry point');
const auth={Authorization:'Bearer manual-fix-preview-key'};
async function openTeam(page,request,width=390,height=844,demo=[[2,'Asked']]){
 await page.setViewportSize({width,height});
 await page.addInitScript(()=>{
  localStorage.setItem('givelife-cloud-key','manual-fix-preview-key');
  localStorage.setItem('givelife-theme','dark');
 });
 await request.post('/__test/seed',{headers:auth,data:{team_demo:demo}});
 await page.goto('/');
 await page.locator('#openTeam').click();
 await expect(page.locator('.team-page')).toBeVisible();
}
test('focused Team field retains text, cursor and keyboard-ready state on resize',async({page,request})=>{
 await openTeam(page,request);
 await page.getByRole('button',{name:'+ Add tasks'}).click();
 const field=page.locator('#teamText');
 await field.fill('Post updates\nContact volunteers\nDeadline in 4 hours');
 await field.focus();await field.evaluate(el=>el.setSelectionRange(7,7));
 await page.setViewportSize({width:389,height:844});
 await page.waitForTimeout(300);
 await expect(field).toBeFocused();
 await expect(field).toHaveValue(/Contact volunteers/);
 expect(await field.evaluate(el=>el.selectionStart)).toBe(7);
});
test('Team polling does not replace a focused text field',async({page,request})=>{
 await openTeam(page,request);
 await page.getByRole('button',{name:'+ Add tasks'}).click();
 const field=page.locator('#teamText');
 await field.fill('Post update\nDeadline in 4 hours');
 await field.focus();
 await page.waitForTimeout(8400);
 await expect(field).toBeFocused();
 await expect(field).toHaveValue(/Post update/);
});
test('Overflowing Team tasks can be expanded and viewed without hidden actions',async({page,request})=>{
 await openTeam(page,request,360,640,[[8,'Reported'],[14,'Asked'],[3,'Late'],[5,'Done']]);
 const button=page.getByRole('button',{name:/Show all/i}).first();
 await expect(button).toBeVisible();
 await button.click();
 await expect(page.locator('.team-page')).toHaveClass(/team-expanded/);
 await expect(page.locator('.team-review .team-item')).toHaveCount(8);
 expect(await page.locator('.team-body').evaluate(el=>getComputedStyle(el).overflowY)).toBe('auto');
});
