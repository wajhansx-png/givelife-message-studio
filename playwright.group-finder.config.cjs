const {defineConfig}=require('@playwright/test');
const port=Number(process.env.GIVELIFE_TEST_PORT||3041);
module.exports=defineConfig({
 testDir:'tests/e2e',testMatch:'group_finder.spec.cjs',workers:1,retries:0,timeout:30000,
 outputDir:'test-results/group-finder',reporter:'list',globalTeardown:require.resolve('./tests/group_finder_teardown.cjs'),
 use:{baseURL:`http://127.0.0.1:${port}`,headless:true,trace:'off'},
 webServer:{command:`python tests/preview_group_finder.py --port ${port}`,url:`http://127.0.0.1:${port}/health`,reuseExistingServer:false,timeout:30000},
});
