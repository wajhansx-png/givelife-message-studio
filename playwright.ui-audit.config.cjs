const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({testDir:'tests/e2e',workers:1,timeout:60000,retries:0,
 use:{baseURL:'http://127.0.0.1:3055',headless:true},reporter:[['list']],outputDir:'test-results/ui-audit',
 ...(process.env.GIVELIFE_UI_EXISTING==='1'?{}:{
  webServer:{command:'python tests/preview_fake.py --donors --test-api --port 3055',url:'http://127.0.0.1:3055/health',reuseExistingServer:false,timeout:30000},
  globalTeardown:require.resolve('./tests/ui_audit_teardown.cjs')
 })});
