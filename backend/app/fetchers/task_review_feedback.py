"""Consume human feedback for every configured task with history learning."""
from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.task_review_learning import consume_pending_feedback


class TaskReviewFeedbackFetcher(DataFetcher):
    def __init__(self):
        super().__init__('task_review_feedback', '任务人工反馈学习', '* * * * *')

    async def fetch_and_store(self):
        await consume_pending_feedback()
