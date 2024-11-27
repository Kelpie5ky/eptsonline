import json
import aiohttp
from aiohttp import ClientSession, FormData
from aiohttp_retry import ExponentialRetry, RetryClient
from user_data import *
from datetime import timedelta
from html import unescape, escape
import io
import os
from PIL import Image
import PIL
from bs4 import BeautifulSoup
import re

class AltImageHandler():
    def __init__(self):
        self.cookie_jar = aiohttp.CookieJar()
        retry_options = ExponentialRetry(attempts=3, max_timeout=5)
        self.session = aiohttp.ClientSession(cookie_jar=self.cookie_jar)
        self.client = RetryClient(raise_for_status=False, retry_options=retry_options, client_session=self.session)

    async def get_item_list(self):
        data = {
            'feeduid': '140522082101',
            'partuid': '',
            'page': '1',
            'items': '500',
            'action': 'feedposts',
        }

        response = await self.client.post('https://feeds.tilda.ru/submit/', cookies=cookies, headers=headers, data=data)
        result = await response.json(content_type=None)
        items = []
        for item in result['data']['posts']:
            items.append(item)
        return items

    async def get_item_data(self, item_id):
        data = {
            'postuid': item_id,
            'action': 'feedpostget',
        }

        response = await self.client.post('https://feeds.tilda.ru/submit/', cookies=cookies, headers=headers, data=data)
        result = await response.json(content_type=None)
        return result['data']

    async def download_and_compress_image(self, url, output_dir="compressed_images"):
        os.makedirs(output_dir, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download image. Status: {response.status}")

                image_data = await response.read()

        # Open and process the image
        with io.BytesIO(image_data) as img_buffer:
            image = Image.open(img_buffer)
            # image = image.convert("RGB")  # Ensure compatibility with JPEG

            # Resize if needed
            max_size = (1600, 1600)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)  # Updated

            output_path = os.path.join(output_dir, os.path.basename(url.split("/")[-1]))
            # if not output_path.endswith(".jpg"):
            #     output_path = os.path.splitext(output_path)[0] + ".jpg"

            with io.BytesIO() as buffer:
                image.save(buffer, format=image.format, quality=70, optimize=True)
                with open(output_path, "wb") as f:
                    f.write(buffer.getvalue())


            original_size = len(image_data) / 1024  # KB
            compressed_size = os.path.getsize(output_path) / 1024  # KB

            print(f"Original image size: {original_size:.2f} KB")
            print(f"Compressed image size: {compressed_size:.2f} KB")
            return output_path

    async def upload_image(self, image_path: str):
        url = 'https://upload.tildacdn.com/api/upload/'
        params = {
            'publickey': 'shgBjffb264Vdv93',
            'uploadkey': '66633566-3262-4532-b531-643639393465',
        }
        headers = {
            'accept': 'application/json',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'origin': 'https://feeds.tilda.ru',
            'referer': 'https://feeds.tilda.ru/',
            'sec-ch-ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }
        retry_options = ExponentialRetry(attempts=3, max_timeout=5)
        session = aiohttp.ClientSession()
        async with RetryClient(raise_for_status=False, retry_options=retry_options, client_session=session) as client:
            with open(image_path, 'rb') as f:
                file_content = io.BytesIO(f.read())
                file_content.seek(0)

            form_data = FormData()
            form_data.add_field('publickey', params['publickey'])
            form_data.add_field('uploadkey', params['uploadkey'])
            form_data.add_field('file', file_content, filename='Ndj2fvdmsk3_33fnsdv.jpg', content_type='image/jpeg')
            async with client.post(url, params=params, headers=headers, data=form_data) as response:
                result = await response.json(content_type=None)
                image_data = result['result'][0]
        return image_data

    async def process_body(self, body, alt_tag):
        images = []
        body = json.loads(body)
        counter = 2
        for item in body:
            if item['ty'] == 'image':
                compressed_image = await self.download_and_compress_image(item['url'])
                new_uploaded_image = await self.upload_image(compressed_image)
                item['url'] = new_uploaded_image['cdnUrl']
                item['alt'] = f"{alt_tag} фото №{counter}"
                counter += 1

        return body

    async def process_text_body(self, body, alt_tag):
        soup = BeautifulSoup(body, 'html.parser')
        img_tags = soup.findAll("img")

        counter = 2

        for img in img_tags:
            img_url = img.get("src")
            if img_url:
                image_path = await self.download_and_compress_image(img_url)
                new_image_url = await self.upload_image(image_path)
                img["src"] = new_image_url['cdnUrl']
                img["alt"] = f"{alt_tag} фото №{counter}"
                counter += 1

        return str(soup)

    async def change_item_data(self, item_data, item_id, date):
        alt_tag = item_data['title']
        print(alt_tag)
        text = item_data['text']
        decoded_text = unescape(text)
        try:
            parsed_json = json.loads(decoded_text)
            dumped_json = json.dumps(parsed_json, ensure_ascii=False, indent=2)
            processed_body = await self.process_body(dumped_json, alt_tag)
            item_data['text'] = json.dumps(processed_body)
        except json.JSONDecodeError:
            processed_body = await self.process_text_body(decoded_text, alt_tag)
            processed_body = processed_body.replace('<br/>', '<br />')
            item_data['text'] = processed_body


        try:
            compressed_image = await self.download_and_compress_image(item_data['image'])
            new_uploaded_image = await self.upload_image(compressed_image)
        except Exception as e:
            new_uploaded_image = {'cdnUrl': ''}
        date = str(date)[:-3]

        if 'казах' in alt_tag.lower():
            parts = "431493355531,766608694561,557733902881,505696001841"
        elif 'беларус' in alt_tag.lower() or 'белорус' in alt_tag.lower():
            parts = "135053026061,766608694561,557733902881,505696001841"
        elif 'эмират' in alt_tag.lower() or 'оаэ' in alt_tag.lower():
            parts = "686560656281,766608694561,557733902881,505696001841"
        elif 'армен' in alt_tag.lower():
            parts = "128961897061,766608694561,557733902881,505696001841"
        elif 'киргиз' in alt_tag.lower() or 'кырг' in alt_tag.lower():
            parts = "590907795991,766608694561,557733902881,505696001841"
        else:
            parts = "579805585971,766608694561,557733902881,505696001841"



        template = {
          "action": "feedpostedit",
          "authorimg": "",
          "authorimgalt": "",
          "authorname": "",
          "authorurl": "",
          "date": f"{date}",
          "descr": item_data['descr'],
          "directlink": "",
          "disableamp": "y",
          "disablerss": "y",
          "fb_descr": "",
          "fb_image": "",
          "fb_imagealt": "",
          "fb_title": "",
          "image": new_uploaded_image['cdnUrl'],
          "imagealt": f"{alt_tag} фото №1",
          "li-tubutton": "",
          "mediadata": new_uploaded_image['cdnUrl'],
          "mediatype": "image",
          "parts": "407128505991",
          "partsselector": "",
          "postuid": item_id,
          "projectid": "5737600",
          "seo_descr": item_data['seo_descr'],
          "seo_keywords": "",
          "seo_title": item_data['seo_title'],
          "text": item_data['text'],
          "thumb": "",
          "thumbalt": "",
          "title": item_data['title'],
          "visibility": "y"
        }
        response = await self.client.post('https://feeds.tilda.ru/submit/', cookies=cookies, headers=headers, data=template)
        result = await response.text()
        print(result)

    async def fetch_image_size(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.head(url, cookies=cookies, headers=headers) as response:
                content_length = response.headers.get('Content-Length')

                if content_length:
                    size_in_bytes = int(content_length)
                    return round(size_in_bytes / 1024, 2)
                else:
                    return None


    async def get_data(self, item_id, item_data):
        body = item_data['text']
        body = unescape(body)
        result = {}
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass

        # Process JSON-like body
        if isinstance(body, list):
            for element in body:
                if element.get('ty') == 'image':
                    url = element.get('url')
                    if url:
                        image_size_kb = await self.fetch_image_size(url)
                        result[url] = {
                            "image_size": f"{image_size_kb} KB",
                            "image_alt_tag": element.get('alt', '')
                        }

        # Process HTML-like body
        elif isinstance(body, str):
            soup = BeautifulSoup(body, 'html.parser')
            figures = soup.find_all('figure', attrs={'contenteditable': 'false'})
            for figure in figures:
                img = figure.find('img')
                if img:
                    src = img.get('src')
                    alt = img.get('alt', '')
                    image_size_kb = await self.fetch_image_size(src)
                    result[src] = {
                        "image_size": f"{image_size_kb} KB",
                        "image_alt_tag": alt
                    }

        return result

