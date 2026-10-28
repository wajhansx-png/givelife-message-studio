const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({
 testDir:'tests/e2e',fullyParallel:false,workers:1,retries:0,timeout:30000,
 use:{baseURL:'http://127.0.0.1:3011',headless:true,trace:'retain-on-failure'},
 webServer:{command:'python tests/preview_fake.py --donors --test-api --port 3011',url:'http://127.0.0.1:3011/health',reuseExistingServer:false,timeout:30000},
 reporter:[['list'],['html',{open:'never'}]],
});

