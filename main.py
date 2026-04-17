import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import pprint

ua = UserAgent()
random_user_agent = ua.random
headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "User-Agent": random_user_agent
}

# with open('data_calendar.html', 'w', encoding="utf-8") as f:
#    f.write(res.text)
#
# with open('data_calendar.html', 'r', encoding="utf-8") as f:
#     res = f.read()

res = requests.get("https://www.championat.com/auto/_f1/tournament/1032/calendar/", headers=headers)
soup = BeautifulSoup(res.text, 'lxml')

calendar = soup.find_all(['td', 'div'], class_=['tournament-calendar__title',
                                                'tournament-calendar__name',
                                                'tournament-calendar__date'])
data = {}
with open('calendar.json', 'w', encoding="utf-8") as json_file:
    ...
for line in calendar:
    if 'Этап' in line.text or 'Зимние' in line.text:
        stage = line.text.strip()
        data[line.text.strip()] = []
        data[stage].append('\n')
    else:
        data[stage].append(line.text.strip())
for key in data.keys():
    ...
    # print(key, ' '.join(data[key]))

res2 = requests.get("https://www.championat.com/auto/_f1/tournament/1032/", headers=headers)
soup2 = BeautifulSoup(res2.text, 'lxml')

top_leaders = soup2.find_all(['span', 'td'], class_=['table-item__name', '_right'])
# for i in range(0, len(top_leaders), 2):
#     print(top_leaders[i].text.strip() + '. Кол-во очков: ' + top_leaders[i + 1].text.strip())

res3 = requests.get("https://www.championat.com/auto/_f1/tournament/1032/players/", headers=headers)
soup3 = BeautifulSoup(res3.text, 'lxml')

pilots = soup3.find_all(['span', 'td'], class_=['table-item__name',
                                                'table-responsive__row-item _player-team _order_2 _order_mobile_4 _tablet',
                                                'table-responsive__row-item _right _order_5 _desktop',
                                                'table-responsive__row-item _right _w-5 _order_6 _desktop',
                                                'table-responsive__row-item _right _w-5 _order_7 _desktop'])

for i in range(0, len(pilots), 5):
    ans = [f'{pilots[i].text.strip()}, {pilots[i + 1].text.strip()}']
    ans.append(f'Дата рождения: {pilots[i + 2].text.strip()}')
    if pilots[i + 3].text.strip():
        ans.append(f'Рост: {pilots[i + 3].text.strip()}')
    if pilots[i + 4].text.strip():
        ans.append(f'Вес: {pilots[i + 4].text.strip()}')
    print('\n'.join(ans))