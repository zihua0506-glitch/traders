import numpy as np
import math
from datetime import datetime

def calculate_tweet_impact(tweet_data: dict, current_time: datetime = None) -> float:
    """
    计算推文的单点影响力分数 (Crypto Social Alpha).
    
    Args:
        tweet_data (dict): 包含推特数据的字典，需包含:
            - 'likes': 点赞数
            - 'replies': 回复数
            - 'retweets': 转推数
            - 'quotes': 引用推文数
            - 'impressions': 浏览量 (View Count)
            - 'followers': 作者粉丝数
            - 'created_at': 推文发布时间 (datetime对象)
            - 'is_verified': 是否蓝标 (bool)
        current_time (datetime): 当前计算时间
    
    Returns:
        float: 影响力分数 (0 - 100+)
    """
    if current_time is None:
        current_time = datetime.now()
        
    # 1. 基础权重 (Weights) - 引用和转推权重更高，因为代表传播
    w_like = 1.0
    w_reply = 2.0
    w_rt = 4.0
    w_quote = 6.0
    
    # 提取数据
    likes = tweet_data.get('likes', 0)
    replies = tweet_data.get('replies', 0)
    rts = tweet_data.get('retweets', 0)
    quotes = tweet_data.get('quotes', 0)
    views = tweet_data.get('impressions', 1)  # 防止除0
    followers = tweet_data.get('followers', 1)
    
    # 2. 互动总分 (Raw Engagement Score)
    engagement_score = (likes * w_like) + (replies * w_reply) + (rts * w_rt) + (quotes * w_quote)
    
    # 3. 真实性检测 (Bot Detection Filter) - 经验性 Alpha
    # 逻辑: 如果互动率高得离谱 (比如 浏览量 100，点赞 50)，通常是刷的。
    # 正常的 Likes/Views 比率通常在 1% - 5% 之间。
    if views > 100:
        engagement_rate_by_view = engagement_score / views
        if engagement_rate_by_view > 0.20: # 超过 20% 的人互动，极大概率是Bot
            engagement_score *= 0.1 # 惩罚
            
    # 4. 影响力基数 (Normalizing)
    # 使用 log(views) 而不是 followers，因为 followers 可以买，views 相对难刷且代表真实触达
    # +1000 是平滑项
    impact_magnitude = engagement_score / np.log10(views + 1000)
    
    # 5. 蓝标/金标加成 (Credibility Bonus)
    if tweet_data.get('is_verified', False):
        impact_magnitude *= 1.2
        
    # 6. 时间衰减 (Time Decay) - 关键 Alpha
    # 金融市场里，消息过时就无效。使用半衰期模型。
    # 假设每 4 小时影响力衰减一半
    time_diff_hours = (current_time - tweet_data['created_at']).total_seconds() / 3600.0
    lambda_decay = np.log(2) / 4 # Half-life of 4 hours
    time_factor = np.exp(-lambda_decay * time_diff_hours)
    
    final_score = impact_magnitude * time_factor
    
    return max(0.0, final_score)