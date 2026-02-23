module.exports = {
  apps: [
    {
      name: 'knowledge-base',
      cwd: '/Users/xuzhi/prod/knowledge-base',
      script: '.venv/bin/uvicorn',
      args: 'app.api.main:app --host 127.0.0.1 --port 8020',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      error_file: '/Users/xuzhi/prod/gateway/logs/knowledge-base-error.log',
      out_file: '/Users/xuzhi/prod/gateway/logs/knowledge-base-out.log',
      log_file: '/Users/xuzhi/prod/gateway/logs/knowledge-base.log',
      time: true,
      env: {
        DATABASE_URL: 'sqlite+aiosqlite:///./data/knowledge.db'
      }
    }
  ]
};
