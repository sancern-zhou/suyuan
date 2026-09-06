"""Worker-owned feedback learning, independent of the daily review poll."""

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.jiangsu_review_learning import consume_pending_feedback


class JiangsuReviewFeedbackFetcher(DataFetcher):
    def __init__(self):
        super().__init__('jiangsu_review_feedback', '故障工单人工反馈学习', '* * * * *')

    async def fetch_and_store(self):
        await consume_pending_feedback()
