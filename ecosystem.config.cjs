module.exports = {
  apps: [
    {
      name: 'adpay',
      script: 'uvicorn',
      args: 'main:app --host 0.0.0.0 --port 3000',
      cwd: '/home/user/webapp',
      interpreter: 'none',
      env: {
        NODE_ENV: 'development',
      },
      watch: false,
      instances: 1,
      exec_mode: 'fork'
    }
  ]
}
