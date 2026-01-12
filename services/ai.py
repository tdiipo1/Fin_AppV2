import os
import json
import logging
import google.generativeai as genai
from sqlalchemy.orm import Session
from database.models import Transaction, Category, CategoryMap

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Gemini
# Expects GOOGLE_API_KEY in environment variables or .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

API_KEY = os.getenv("GOOGLE_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

def get_uncategorized_transactions(db: Session):
    """
    Fetch transactions that have no category_id.
    """
    return db.query(Transaction).filter(Transaction.category_id == None).all()

def generate_prompt(descriptions: list, categories: list) -> str:
    """
    Constructs the prompt for Gemini.
    """
    # Create taxonomy string
    taxonomy_str = ""
    for c in categories:
        sub = f" > {c.subcategory}" if c.subcategory else ""
        taxonomy_str += f"- ID: {c.id} | Path: {c.section} > {c.category}{sub}\n"

    # Create transactions string
    tx_str = "\n".join([f"- {d}" for d in descriptions])

    prompt = f"""
    You are a financial categorization assistant. match the following transaction descriptions to the most appropriate Category ID from the provided Taxonomy.
    
    ### Taxonomy (ID | Path):
    {taxonomy_str}
    
    ### Transactions to Categorize:
    {tx_str}
    
    ### Instructions:
    1. Analyze each transaction description.
    2. Select the BEST fit Category ID from the Taxonomy.
    3. If there is absolutely no match or it is a transfer/payment that shouldn't be categorized as expense/income, you can use null or skip.
    4. Return ONLY a JSON list of objects. Do not include markdown formatting (like ```json).
    5. Each object must have:
       - "description": The exact input description string.
       - "category_id": The ID from the taxonomy.
    
    ### Output Format:
    [
        {{"description": "WALMART STORE 123", "category_id": "SCSC1234"}},
        ...
    ]
    """
    return prompt

def run_auto_categorization(db: Session, batch_size=50):
    """
    Main entry point. Fetches uncategorized txs, calls AI, updates DB.
    Returns (processed_count, success_count)
    """
    if not API_KEY:
        logger.error("No Google API Key found.")
        return 0, 0

    # 1. Fetch Data
    uncategorized_txs = get_uncategorized_transactions(db)
    if not uncategorized_txs:
        logger.info("No uncategorized transactions found.")
        return 0, 0

    # Get unique descriptions to save tokens/calls
    # We only map UNIQUE descriptions.
    unique_descs = list(set([t.raw_description or t.description for t in uncategorized_txs if (t.raw_description or t.description)]))
    
    logger.info(f"Found {len(uncategorized_txs)} transactions with {len(unique_descs)} unique descriptions.")

    # Fetch Taxonomy
    categories = db.query(Category).all()
    
    # 2. Batch Process
    total_processed = 0
    total_updates = 0
    
    # Process in chunks
    for i in range(0, len(unique_descs), batch_size):
        batch = unique_descs[i : i + batch_size]
        logger.info(f"Processing batch {i} to {i+len(batch)}...")
        
        prompt = generate_prompt(batch, categories)
        
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            
            # Clean response (sometimes gemini puts ```json ... ```)
            content = response.text.replace("```json", "").replace("```", "").strip()
            
            mappings = json.loads(content)
            
            # 3. Update DB
            for item in mappings:
                desc_str = item.get('description')
                cat_id = item.get('category_id')
                
                if desc_str and cat_id:
                    # Validate Cat ID exists
                    valid_cat = db.query(Category).filter(Category.id == cat_id).first()
                    if not valid_cat:
                        continue
                        
                    # A. Update ALL matching transactions
                    # We match on raw_description OR description depending on what we sent.
                    # We sent raw if available.
                    # Update transactions where raw_desc matches OR description matches 
                    # (Simple logic: just update ones where field matches the prompt input)
                    
                    # Find txs to update
                    txs_to_update = db.query(Transaction).filter(
                        (Transaction.raw_description == desc_str) | (Transaction.description == desc_str),
                        Transaction.category_id == None
                    ).all()
                    
                    for tx in txs_to_update:
                        tx.category_id = cat_id
                        total_processed += 1
                        
                    # B. Save to CategoryMap (Memory)
                    # Check if rule exists
                    existing_rule = db.query(CategoryMap).filter(CategoryMap.unmapped_description == desc_str).first()
                    if not existing_rule:
                        new_rule = CategoryMap(unmapped_description=desc_str, scsc_id=cat_id)
                        db.add(new_rule)
                        total_updates += 1
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            continue

    return total_processed, total_updates
