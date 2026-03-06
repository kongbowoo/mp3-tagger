# 上传到 GitHub - 快速指南

## 当前状态

✅ Git 仓库已初始化
✅ 已有 3 个提交
✅ .gitignore 已配置

## 上传步骤

### 步骤 1：创建 GitHub 仓库

1. 访问 https://github.com/new
2. 填写：
   - Repository name: `mp3-tagger`
   - Description: `MP3 标签整理工具 - 自动重命名为「艺术家 - 标题」格式`
   - 选择 **Public**（公开）
3. 点击 **Create repository**
4. **不要** 勾选 README/.gitignore/许可证

### 步骤 2：推送代码

创建后，GitHub 会显示推送命令，执行：

```bash
cd D:\Music\code\mp3-tagger

# 添加远程仓库（替换 YOUR_USERNAME 为你的 GitHub 用户名）
git remote add origin https://github.com/YOUR_USERNAME/mp3-tagger.git

# 重命名分支为主分支
git branch -M main

# 推送到 GitHub
git push -u origin main
```

### 步骤 3：验证

访问你的仓库：
```
https://github.com/YOUR_USERNAME/mp3-tagger
```

## 常见问题

### Q: Git 报错 "remote origin already exists"
A: 执行 `git remote set-url origin https://github.com/YOUR_USERNAME/mp3-tagger.git`

### Q: 推送失败，提示认证
A: 需要使用 Personal Access Token：
   1. GitHub → Settings → Developer settings → Personal access tokens
   2. 生成新 token（勾选 repo 权限）
   3. 使用 token 代替密码

### Q: 网络连接超时
A: 可以尝试：
   - 使用代理
   - 修改 hosts 文件
   - 使用 [Fast GitHub](https://github.com/dotnetcore/FastGithub)

## 项目文件

```
mp3-tagger/
├── README.md          # 使用说明
├── config.json        # 配置（不含敏感信息）
├── requirements.txt   # Python 依赖
├── gui_main.py        # 图形界面
├── mb_search.py       # 命令行搜索
├── id3_cli.py         # 命令行 ID3
├── full_tagger.py     # 命令行指纹
└── .gitignore
```

## 安全提示

`config.json` 中的 API Key 已包含在仓库中。如果是私有仓库没问题，如果是公开仓库建议：

1. 删除 API Key：编辑 `config.json` 改为 `"acoustid_api_key": ""`
2. 创建 `.env.example` 模板文件
3. 将 `config.json` 加入 `.gitignore`

或者直接将仓库设为 **私有**（Private）。
