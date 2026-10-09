# 推送到 GitHub 的命令（逐条复制粘贴）

前提：已在 https://github.com/new 建好仓库，名字用 `garbage-sorting-prototype`，
可见性选 **Public**，**不要**勾选 "Add a README" 或 .gitignore 模板。

---

## 第一步：把「你的用户名」换成你的 GitHub 用户名

在开始菜单搜 `PowerShell`，打开后依次粘贴下面四条（每条回车一次）：

```powershell
cd "C:\Users\15040\Documents\ChatGPT\全球校园人工智能算法精英"
```

```powershell
git config user.name "你的GitHub用户名"
git config user.email "你的GitHub注册邮箱"
```

```powershell
git commit -m "智识固废：垃圾分类视觉识别与投放引导：原型 + 作品介绍页 + 数据大屏"
```

```powershell
git branch -M main
```

---

## 第二步：关联仓库并推送

把下面这条里的 `你的用户名` 换成你的 GitHub 用户名（两处都要换），再粘贴回车：

```powershell
git remote add origin https://github.com/你的用户名/garbage-sorting-prototype.git
```

```powershell
git push -u origin main
```

**第一次推送会弹出浏览器窗口**，让你登录 GitHub 授权（Git Credential Manager），
登录一次以后就记住了。等终端显示 `main -> main` 之类的字样就是成功了。

---

## 如果中途报错

| 报错 | 原因 | 处理 |
| --- | --- | --- |
| `remote origin already exists` | 之前加过 | 先执行 `git remote remove origin` 再加一次 |
| `Authentication failed` | 没登录成功 | 重新执行 `git push -u origin main`，在弹出的窗口里登录 |
| `src refspec main does not match any` | 漏了 commit 那步 | 回到第一步，把 commit 那条再执行一次 |
| `LF will be replaced by CRLF` 一大堆警告 | 换行符提示，不是错误 | 忽略即可 |

---

## 推送成功后

1. 到仓库页确认文件已在（应该能看到 `prototype/`、`docs/`、`render.yaml`）
2. 按 [上线部署说明.md](上线部署说明.md) 的第 3 步开 Pages、第 4 步建 Render 服务
3. 把 Render 给你的地址发我，我更新跳转页
