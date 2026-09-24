这是整个rss阅读器的页面说明

# 1.页面结构如下所示:

```
- login page
    - email+password sign up
    - login
- reader page
    - left router sidebar
    - right main content area
```

# 2.登录页

注册和登录允许跳过，跳过后每次登录默认为用户user
用户数据存放在本地，允许导出

## 2.1 注册

schema: username, email, password

## 2.2 登录

schema: email, password

# 3.阅读器页

## 3.1 左侧边栏(路由)

从上到下依次为:
    web-logo, web-title
    rss source management
    user profile

### 3.1.1 web-logo, web-title放在一排

### 3.1.2 rss source management

界面最复杂的功能为路由

路由层级为:
1. all, essays, pictures, videos
2. 收藏(默认存在，不可修改，删除的目录), rss directorys(包含多个rss，由用户创建)
3. rss source(rss source logo, name)
4. essay, picture, video item
5. content

这里主要是第1,2,3这几个层级，相当于分层过滤

- 刚登录默认为all，此时显示所有的用户创建的rss directorys, 收藏目录, 还有未分组的rss source
点击essays, pictures, videos会对all中的所有rss源按照类别进行过滤

- 再选择收藏目录或者rss目录，根据上一级路由来确定, 它们之间是&关系，例如all->收藏,意味着所有收藏的rss文章,图片或者视频, videos->收藏为收藏的视频，点击目录也一样，例如all->目录名为目录中所有类型的源

- 第三层为rss source的item, 显示当前目录下所有源的 (logo, name)



### 3.1.3 user profile
这个区域展示user_headImg, username
点击后在上方展示profile menu
整个profile menu包含 profile(headimg, username, email), settings(点击后打开 settings modal), logout三个可选项，
如果skip登录的情况下，email为'example@example.com'

profile点击后弹窗，可以修改头像，用户名，头像默认为用户名首字母+5种纯色背景，也可以从本地上传不超过3mb图片(png, jpg), 邮件为用户身份
标识，不可编辑

#### 3.1.4 settings modal
- appearance(外观, 包含theme(light, dark), language(chinese, english), text style)
- rss(数据管理(导入/导出订阅源), 管理订阅(添加订阅，删除选中，编辑订阅源))
- ai(ai配置(provider, url, api key, model，可能接入多个供应商), token使用量,设置上限)
- integration(自建rsshub(需要配置服务相关参数rsshub url:port，env), obsidian(文件路径), feishu webhook(webhook url), custom export(url, schema))
- automization(when if then结构，可以添加多个规则)
- proxy(代理配置,默认,本地http, https, no_proxy代理，可以自定义ip:port,..)

## 3.2 主要内容区
这里根据左侧边栏的rss source management的选择来路由

- 当是一级路由是all或者essays时主要内容区为:
左右两栏，左栏为essays，pictures, videos消息列表(rss source logo&title, update time, essay title),左栏顶部有刷新，已读，未读，可以往下滑动
右侧为左栏中所选择的essay，picture, video的内容，阅读器的主要阅读部分，有以下功能:

阅读区包含顶栏的标记为已读，收藏，分享，导出(pdf, markdown)，正文schema: {title, rss-logo,rss-name, author, update_time, content}, essay补充一个当前阅读进度，当前/总字数的显示
还有ai相关的总结，标题翻译功能, video,picture不需要

- 当一级路由是pictures时，主要内容为一个瀑布列表(图片大小不同，不可能用网格平铺)，6列，item(图片,title,update_time),同样支持滑动

- 当一级路由是videos时，主要内容区域为grid list，每行有5个视频，包含(封面，title, author, channel name, update time)，也支持滑动

其它情况:
- 一级路由为all, 点击目录/收藏时，展示左右两栏的内容区，左边条目右边条目具体内容
- 目录中有多种不同类型的rss source时，按照左右两栏的方式显示内容


左侧边栏和主要内容区之间可以通过鼠标拖动调整左右比例。
