import asyncio
import json
from EptsAltOfImageHandler import AltImageHandler
from datetime import datetime, timedelta
import csv
import os

csv_file = 'output.csv'


def get_processed_item_ids():
    if os.path.exists(csv_file):
        processed_ids = set()
        with open(csv_file, 'r', encoding='utf-8') as csvfile:
            csv_reader = csv.reader(csvfile)
            next(csv_reader)
            for row in csv_reader:
                processed_ids.add(row[0])
        return processed_ids
    return set()


async def main():
    image_handler = AltImageHandler()
    items = await image_handler.get_item_list()

    start_date = "2024-11-26"
    current_date = datetime.strptime(start_date, "%Y-%m-%d")

    with open('alt_tags.json', 'r', encoding='UTF-8') as f:
        alt_tags = json.load(f)

    try:
        with open('processed_ids.json', 'r', encoding='UTF-8') as f:
            processed_ids = set(json.load(f))
    except FileNotFoundError:
        processed_ids = set()

    processed_item_ids = get_processed_item_ids()

    with open(csv_file, 'a', newline='', encoding='utf-8') as csvfile:
        csv_writer = csv.writer(csvfile)

        # Write header if file is empty (i.e., first run)
        if os.stat(csv_file).st_size == 0:
            csv_writer.writerow(['ItemId', 'Url', 'AltTag', 'ImageSize'])

        counter = 1
        for item_id in items:
            print(f"Processing item {counter}")
            counter += 1

            if item_id in processed_item_ids:
                print(f"Item {item_id} already processed. Skipping.")
                continue

            item_data = await image_handler.get_item_data(item_id)
            data = await image_handler.get_data(item_id, item_data)

            for url, details in data.items():
                image_size = details['image_size']
                image_alt_tag = details['image_alt_tag']

                csv_writer.writerow([item_id, url, image_alt_tag, image_size])

            processed_item_ids.add(item_id)

            with open('processed_ids.json', 'w', encoding='UTF-8') as f:
                json.dump(list(processed_item_ids), f, ensure_ascii=False, indent=4)

    print("Data processing and writing complete.")

    await image_handler.client.close()


asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
