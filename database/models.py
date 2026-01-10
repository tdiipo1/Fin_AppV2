from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from .connection import Base
import hashlib

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    scsc_id = Column(String, unique=True, index=True) # e.g. "Housing::Rent::Base"
    section = Column(String, nullable=False)
    category = Column(String, nullable=False)
    subcategory = Column(String, nullable=True)

    transactions = relationship("Transaction", back_populates="category")
    mappings = relationship("MappingRule", back_populates="category")

    def __repr__(self):
        return f"<Category {self.scsc_id}>"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    
    # Validation / Linking
    simplefin_id = Column(String, unique=True, nullable=True, index=True)
    fingerprint = Column(String, unique=True, nullable=False, index=True) # SHA256 of date+amount+desc
    
    # Core Data
    date = Column(DateTime, nullable=False, index=True)
    amount = Column(Float, nullable=False) # Negative = Expense, Positive = Income
    description = Column(String, nullable=False) # The main display description
    raw_description = Column(String, nullable=True) # Original raw text from bank
    type = Column(String, nullable=True) # e.g. 'Payment', 'Sale', 'ACH_CREDIT'
    
    # Metadata
    # 'source' in SimpleFin CSV = The Account Name (e.g. "Chase Bank - TOTAL CHECKING")
    # 'import_method' = how it got here ('csv', 'simplefin_api', 'manual')
    account_name = Column(String, nullable=True, index=True) 
    import_method = Column(String, default="csv") 
    
    # AI/Normalization
    clean_description = Column(String, nullable=True)
    standardized_merchant = Column(String, nullable=True)
    
    # Foreign Keys
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    
    # Relationships
    category = relationship("Category", back_populates="transactions")

    @staticmethod
    def generate_fingerprint(date_str: str, amount: float, description: str) -> str:
        """
        Create a deterministic hash to identify a transaction across sources.
        """
        # Normalize inputs
        # Truncate description to avoid minor bank-suffix variations, 
        # though exact match is safer for now to avoid false positives.
        # We use strict Date + Amount + Full Description for safety.
        raw_str = f"{date_str}|{float(amount):.2f}|{description.strip()}"
        return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

    def __repr__(self):
        return f"<Transaction {self.date} - {self.description} - {self.amount}>"


class MappingRule(Base):
    """
    Stores learned associations between raw descriptions and categories/merchants.
    Used for the AI 'Memory'.
    """
    __tablename__ = "mapping_rules"

    id = Column(Integer, primary_key=True, index=True)
    
    # The trigger
    raw_text_pattern = Column(String, unique=True, nullable=False, index=True) # The description to match
    
    # The result
    target_merchant = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    
    # Meta
    is_regex = Column(Boolean, default=False)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("Category", back_populates="mappings")

class SystemLog(Base):
    """
    For persistent logging of sync events.
    """
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String, default="INFO")
    component = Column(String) # 'simplefin', 'importer', 'ai'
    message = Column(String)
