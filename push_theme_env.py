import time
import requests

ACCOUNTS = ["subscription.ajp", "matao.goa", "beingujarati", "asquaredcorporation", "almycontacts",
            "6s.akshayp", "eplofficial2", "thestartupcom", "thetypewriterstales", "secajp04"]
API_KEYS = ["rnd_sB1tXXWyZexZpNmamC3FROw9NThH", "rnd_tMp4KVBW6611dWAGW73whqhrwJC9", "rnd_4d2kFSghPHUYFuz8WK0c7ugrlzzN",
            "rnd_5p6YeJrtrIW4Y0mR3f2iMNmCyUsZ", "rnd_NpPkPi3sqOdkWvd0rdInGUhV1Exr", "rnd_4SZyaCCr7AaUmNgZYNFWPCl3bTRA",
            "rnd_Uk5GN840n0gE9DguD35DkId70tSh", "rnd_y43VJoPwmifVaJqb5mKCTCIDAt1S", "rnd_zujruNfK5nGD1BogTPaxA8RPqii3",
            "rnd_nyZvps68uWTJZVA1YnDRpYrV3ntX"]

# one theme per account - match whatever you set in render_bandwidth.theme
THEMES = {
    "subscription.ajp": "epl-night",
    "matao.goa": "graphite-gold",
    "beingujarati": "dark",
    "asquaredcorporation": "light",
    "almycontacts": "warm-ivory",
    "6s.akshayp": "clean-broadcast",
    "eplofficial2": "cobalt-flame",
    "thestartupcom": "carbon-lime",
    "thetypewriterstales": "plum-copper",
    "secajp04": "arctic-mango",
}

for account, api_key in zip(ACCOUNTS, API_KEYS):
    theme = THEMES.get(account)
    if not theme:
        continue

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": "Bearer " + api_key,
    }

    r = requests.get(
        "https://api.render.com/v1/services?type=web_service&includePreviews=true&limit=20",
        headers=headers,
    )
    service_id = r.json()[0]["service"]["id"]

    url = f"https://api.render.com/v1/services/{service_id}/env-vars/THEME_OVERRIDE"
    resp = requests.put(url, json={"value": theme}, headers=headers)
    status = "OK" if resp.status_code in (200, 201) else f"FAILED ({resp.status_code})"
    print(f"{account} [{service_id}] THEME_OVERRIDE={theme}: {status}")
    time.sleep(1)
