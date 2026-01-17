from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from .connection import Base
import hashlib

class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, index=True) # e.g. "SCSC0001"
    section = Column(String, nullable=False)
    category = Column(String, nullable=False)
    subcategory = Column(String, nullable=True)

    transactions = relationship("Transaction", back_populates="category")
    category_maps = relationship("CategoryMap", back_populates="category")
    budgets = relationship("Budget", back_populates="category")

    def __repr__(self):
        return f"<Category {self.id} - {self.category}>"

class MerchantMap(Base):
    __tablename__ = "merchant_maps" # Name not specified, but plural is standard
    
    id = Column(Integer, primary_key=True, index=True)
    raw_description = Column(String, unique=True, nullable=False, index=True)
    standardized_merchant = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

class CategoryMap(Base):
    __tablename__ = "category_maps"
    
    id = Column(Integer, primary_key=True, index=True)
    unmapped_description = Column(String, unique=True, nullable=False, index=True)
    scsc_id = Column(String, ForeignKey("categories.id"), nullable=False, index=True)
    source = Column(String, default='manual') # 'manual', 'ai', 'import'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    category = relationship("Category", back_populates="category_maps")

class Budget(Base):
    __tablename__ = "budgets"
    
    id = Column(Integer, primary_key=True, index=True)
    scsc_id = Column(String, ForeignKey("categories.id"), nullable=False, unique=True)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    note = Column(String, nullable=True)
    
    category = relationship("Category", back_populates="budgets")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    
    # Validation / Linking
    simplefin_id = Column(String, unique=True, nullable=True, index=True)
    # Removed unique=True to allow valid duplicates (e.g. 2 identical purchases) if IDs differ
    fingerprint = Column(String, unique=False, nullable=False, index=True) 
    
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
    source_file = Column(String, nullable=True) # Filename for CSVs, or 'SimpleFin' for API
 
    
    # AI/Normalization
    clean_description = Column(String, nullable=True)
    standardized_merchant = Column(String, nullable=True, index=True)
    is_excluded = Column(Boolean, default=False, index=True)
    
    # Validation / Linking
    merchant_map_id = Column(Integer, ForeignKey("merchant_maps.id"), nullable=True)
    category_map_id = Column(Integer, ForeignKey("category_maps.id"), nullable=True)

    # Foreign Keys
    category_id = Column(String, ForeignKey("categories.id"), nullable=True, index=True) # This is scsc_id alias effectively
    
    category = relationship("Category", back_populates="transactions")
    # merchant_map = relationship("MerchantMap") # Optional loop back
    # category_map = relationship("CategoryMap") # Optional loop back

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

class ExclusionRule(Base):
    __tablename__ = "exclusion_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_type = Column(String, nullable=False, default='exact_match') # 'exact_match', 'regex', 'category'
    value = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, default=True)

class SystemLog(Base):
    """
    For persistent logging of sync events.
    """
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String, default="INFO")
    
class AppSettings(Base):
    """
    Store key-value pairs for application settings.
    """
    __tablename__ = "app_settings"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    component = Column(String) # 'simplefin', 'importer', 'ai'
    message = Column(String)

class StagedTransaction(Base):
    __tablename__ = 'staged_transactions'
    
    id = Column(Integer, primary_key=True)
    external_id = Column(String, unique=True, index=True) # The unique ID from SimpleFin (account_id + transaction_id)
    date = Column(DateTime)
    description = Column(String) # The raw description
    amount = Column(Float)
    account_name = Column(String) # e.g. "Chase - Checking"
    status = Column(String, default="pending") # "pending", "approved", "rejected"
    
    # Metadata
    fetched_at = Column(DateTime, default=datetime.utcnow)
