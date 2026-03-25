# 智能书籍推荐系统（Streamlit）

## 功能
- 首页推荐：热门书籍 + 协同过滤个性化推荐
- 分类筛选与关键字搜索
- 书籍详情页与用户评价
- 收藏功能
- 分页导航

## 运行方式
```bash
pip install -r requirements.txt
streamlit run book_recommender/app.py
```

默认会自动初始化 SQLite 数据库：`book_recommender/books.db`。
