"""招投标信息抓取 Fetcher。"""

from app.fetchers.tenders.tender_information_fetcher import TenderInformationFetcher
from app.fetchers.tenders.monthly_tender_fetcher import MonthlyTenderInformationFetcher

__all__ = ["TenderInformationFetcher", "MonthlyTenderInformationFetcher"]
