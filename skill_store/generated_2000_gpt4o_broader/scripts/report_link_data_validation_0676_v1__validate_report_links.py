def run(context):
    import requests
    url = context['inputs']['url']
    try:
        response = requests.head(url)
        return {'is_valid': response.status_code == 200, 'status_code': response.status_code}
    except requests.RequestException:
        return {'is_valid': False, 'status_code': None}