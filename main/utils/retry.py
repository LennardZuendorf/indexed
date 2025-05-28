import time

def execute_with_retry(func, func_identifier, retries=3, delay=1):
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            print(f'Attempt of "{func_identifier}" number {attempt + 1} failed: {e}')
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                print(f"All {retries} attempts failed.")
                raise e