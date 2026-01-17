import requests
import base64
from urllib.parse import urlparse
import re
from datetime import datetime, timedelta

class SimpleFin:
    @staticmethod
    def claim_setup_token(setup_token: str) -> str:
        """
        Exchanges a setup token for an access URL.
        Returns the access URL.
        """
        claim_url = "https://bridge.simplefin.org/simplefin/claim"
        response = requests.post(claim_url, data=setup_token)
        
        if response.status_code == 200:
            return response.text.strip()
        else:
            raise Exception(f"Failed to claim token: {response.text}")

    @staticmethod
    def clean_description(desc):
        if not desc: return ""
        desc = str(desc).upper()
        desc = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', desc) # Remove dates
        desc = re.sub(r'#?\d{4,}', '', desc) # Remove long IDs
        desc = re.sub(r'STORE\s*\d+', '', desc) # Remove Store #
        return desc.strip()

    @staticmethod
    def fetch_transactions(access_url: str, start_date: datetime, end_date: datetime = None) -> dict:
        """
        Fetches transactions from SimpleFin.
        Handles pagination (60 day max per request).
        """
        if end_date is None:
            end_date = datetime.now()
            
        # Parse connection details
        parsed = urlparse(access_url)
        scheme = parsed.scheme
        netloc = parsed.netloc
        path = parsed.path
        
        # Extract credentials
        if '@' in netloc:
            creds, host = netloc.split('@')
            username, password = creds.split(':')
            base_url = f"{scheme}://{host}{path}"
        else:
            raise ValueError("Invalid Access URL format")

        auth = (username, password)
        
        all_transactions = []
        all_accounts = {} # Map ID -> Name
        
        # Loop in 50 day chunks to be safe (limit is 60)
        current_start = start_date
        
        while current_start < end_date:
            current_end = min(current_start + timedelta(days=50), end_date)
            
            # SimpleFin API requires sdate/edate timestamp parameters if filtering
            # But the 'account' endpoint returns current state. 
            # Actually, standard SimpleFin access URL returns EVERYTHING unless params used?
            # Docs say: /accounts with ?start_date=X&end_date=Y timestamps
            
            params = {
                "start-date": int(current_start.timestamp()),
                "end-date": int(current_end.timestamp())
            }
            
            print(f"Fetching SimpleFin: {current_start.date()} to {current_end.date()}")
            
            try:
                resp = requests.get(f"{base_url}/accounts", auth=auth, params=params)
                if resp.status_code != 200:
                    print(f"Error fetching: {resp.status_code} - {resp.text}")
                    # Skip to next chunk? Or break?
                    break
                    
                data = resp.json()
                
                # Parse Accounts
                for acct in data.get('accounts', []):
                    # "org" key has bank name, "name" has account name
                    org = acct.get('org', {}).get('name', 'Bank')
                    name = acct.get('name', 'Account')
                    full_name = f"{org} - {name}"
                    all_accounts[acct['id']] = full_name
                    
                    # Parse Transactions
                    for tx in acct.get('transactions', []):
                        # Add account_id to tx for linking
                        tx['account_id'] = acct['id']
                        all_transactions.append(tx)
                        
            except Exception as e:
                print(f"Exception during fetch: {e}")
                
            # Advance
            current_start = current_end + timedelta(days=1) # Next day

        return {
            "accounts": all_accounts,
            "transactions": all_transactions
        }
