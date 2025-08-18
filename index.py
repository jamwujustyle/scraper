import requests
import re
import json
from collections import Counter
import os


def get_browser_session():
    # set headers and cookies to get more records from request
    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-GB,en;q=0.9,ru;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-CH-UA": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.blast.hk/",
        }
    )

    cookies = {
        "__ddg9_": "90.156.164.216",
        "__ddg1_": "6yi4LE89vhSX0ET6MrCE",
        "xf_csrf": "F8vpbXFcLmiQrPvf",
        "_gid": "GA1.2.261284424.1755500641",
        "__ddg10_": "1755500936",
        "__ddg8_": "hxwwpwdsaI00WqY7",
        "_gat_gtag_UA_105570047_1": "1",
        "_ga_EZ835TD1Q9": "GS2.1.1755500640$o1$g1$t1755500936$j59$l0$h0",
        "_ga": "GA1.1.108148106.1755500641",
    }

    for name, value in cookies.items():
        session.cookies.set(name, value, domain="www.blast.hk")

    return session


def get_html_with_browser_session(url):
    session = get_browser_session()

    try:
        print(f"Fetching: {url}")
        response = session.get(url, timeout=15)
        response.raise_for_status()

        return response.text
    # ●​ Handle possible errors (e.g., if a page cannot be opened) as per requirement
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def parse_activity_feed(html):
    # get thread ids
    threads = []

    # find activities with dotall cuz html's got multiline elements
    activity_items = re.findall(
        r'<li class="block-row.*?".*?>(.*?)</li>', html, re.DOTALL
    )

    print(f"Found {len(activity_items)} activity items")
    session = get_browser_session()

    for item in activity_items:
        title_div_match = re.search(
            r'<div class="contentRow-title">(.*?)</div>', item, re.DOTALL
        )
        if not title_div_match:
            continue

        title_html = title_div_match.group(1)
        links = re.findall(r'<a href="([^"]+)"', title_html)
        if not links:
            continue

        target_link = links[-1]

        # Extract title from the last link
        title_match = re.search(
            r'<a href="' + re.escape(target_link) + r'"[^>]*>(.*?)</a>', title_html
        )
        topic_title = title_match.group(1).strip() if title_match else "Unknown Title"
        topic_title = re.sub(r"<[^>]+>", "", topic_title).strip()
        topic_title = topic_title.replace("&nbsp;", " ")

        thread_id = None
        if "/threads/" in target_link:
            thread_match = re.search(r"/threads/(\d+)/", target_link)
            if thread_match:
                thread_id = thread_match.group(1)
        elif "/posts/" in target_link:
            try:
                full_url = "https://www.blast.hk" + target_link
                print(f"Resolving post URL: {full_url}")
                response = session.head(full_url, allow_redirects=True, timeout=10)
                redirected_url = response.url
                thread_match = re.search(r"/threads/(\d+)/", redirected_url)
                if thread_match:
                    thread_id = thread_match.group(1)
            except requests.exceptions.RequestException as e:
                print(f"Error resolving post URL {full_url}: {e}")

        if thread_id:
            threads.append((thread_id, topic_title))

    seen = set()
    unique_threads = []
    for thread_id, title in threads:
        if thread_id not in seen:
            seen.add(thread_id)
            unique_threads.append((thread_id, title))

    return unique_threads


def get_last_page_url(thread_id):
    # last page from a thread
    thread_url = f"https://www.blast.hk/threads/{thread_id}/"
    html = get_html_with_browser_session(thread_url)
    if not html:
        return None, None

    # Regex to find the topic title
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    topic_title = title_match.group(1).strip() if title_match else "Unknown Title"
    topic_title = topic_title.replace("&nbsp;", " ")

    # Regex to find the last page number within the thread's page
    page_nav_pattern = re.compile(
        r'href="/threads/' + re.escape(str(thread_id)) + r'/page-(\d+)"'
    )
    page_numbers = [int(p) for p in page_nav_pattern.findall(html)]

    last_page = max(page_numbers) if page_numbers else 1

    return f"{thread_url}page-{last_page}", topic_title


def parse_last_page(html, topic_title):
    """Parses messages from the last page of a thread."""
    messages = []
    nicknames = set()

    message_patterns = [
        r'<article class="message.*?message--post.*?>(.*?)</article>',
    ]

    message_blocks = []
    for pattern in message_patterns:
        blocks = re.findall(pattern, html, re.DOTALL)
        if blocks:
            message_blocks = blocks
            break

    print(f"Found {len(message_blocks)} message blocks in {topic_title}")

    for block in message_blocks:
        author_match = (
            re.search(r'data-author="(.*?)"', block)
            or re.search(r'class="username.*?".*?>(.*?)</.*?>', block)
            or re.search(r'<h4.*?class=".*?username.*?".*?>(.*?)</h4>', block)
        )

        date_match = (
            re.search(r'<time.*?datetime="(.*?)".*?>', block)
            or re.search(r'data-time="(.*?)"', block)
            or re.search(r'<span.*?class=".*?date.*?".*?>(.*?)</span>', block)
        )

        text_match = re.search(
            r'<div class="bbWrapper">(.*?)</div>\s*<div class="js-selectToQuoteEnd">',
            block,
            re.DOTALL,
        )

        if author_match and text_match:
            text_content = text_match.group(1)

            message_parts = []

            parts = re.split(
                r"(<pre.*?<code>.*?</code></pre>)", text_content, flags=re.DOTALL
            )

            for part in parts:
                if not part:
                    continue

                code_match = re.search(
                    r"<pre.*?<code>(.*?)</code></pre>", part, flags=re.DOTALL
                )
                if code_match:
                    code_content = code_match.group(1)
                    code_content = re.sub(r"&quot;", '"', code_content)
                    code_content = re.sub(r"&amp;", "&", code_content)
                    code_content = re.sub(r"&lt;", "<", code_content)
                    code_content = re.sub(r"&gt;", ">", code_content)
                    code_content = re.sub(r"&nbsp;", " ", code_content)
                    message_parts.append(
                        {"type": "code", "content": code_content.strip()}
                    )
                else:
                    cleaned_text = re.sub(
                        r"<(script|style).*?>.*?</\1>",
                        "",
                        part,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    cleaned_text = re.sub(
                        r'<span class="bbCodeInlineSpoiler".*?>(.*?)</span>',
                        r"\1",
                        cleaned_text,
                        flags=re.DOTALL,
                    )
                    cleaned_text = re.sub(
                        r"<blockquote.*?</blockquote>",
                        "",
                        cleaned_text,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    cleaned_text = re.sub(
                        r'<div class="bbCodeBlock-header">.*?</div>',
                        "",
                        cleaned_text,
                        flags=re.DOTALL,
                    )
                    cleaned_text = re.sub(
                        r"<br\s*/?>", "\n", cleaned_text, flags=re.IGNORECASE
                    )
                    cleaned_text = re.sub(
                        r"</p>", "\n", cleaned_text, flags=re.IGNORECASE
                    )
                    cleaned_text = re.sub(
                        r"</div>", "\n", cleaned_text, flags=re.IGNORECASE
                    )
                    cleaned_text = re.sub(r"<[^>]+>", " ", cleaned_text)
                    cleaned_text = re.sub(r"&quot;", '"', cleaned_text)
                    cleaned_text = re.sub(r"&amp;", "&", cleaned_text)
                    cleaned_text = re.sub(r"&lt;", "<", cleaned_text)
                    cleaned_text = re.sub(r"&gt;", ">", cleaned_text)
                    cleaned_text = re.sub(r"&nbsp;", " ", cleaned_text)
                    cleaned_text = re.sub(r"&#\d+;", " ", cleaned_text)
                    cleaned_text = cleaned_text.replace("\t", " ")
                    cleaned_text = re.sub(r" +", " ", cleaned_text)
                    cleaned_text = re.sub(r"(\s*\n\s*){2,}", "\n\n", cleaned_text)
                    cleaned_text = cleaned_text.strip()
                    cleaned_text = re.sub(
                        r"^.*?написал\(а\):", "", cleaned_text
                    ).strip()

                    if cleaned_text:
                        message_parts.append({"type": "text", "content": cleaned_text})

            if any(part.get("content") for part in message_parts):
                author_name = re.sub(r"<[^>]+>", "", author_match.group(1)).strip()
                nicknames.add(author_name.lower())
                message = {
                    "author": author_name,
                    "datetime": (
                        date_match.group(1).strip() if date_match else "Unknown"
                    ),
                    "text": message_parts,
                }
                messages.append(message)
                if message_parts:
                    print(
                        f"Extracted message from {author_name}: {message_parts[0].get('content', '')[:100]}..."
                    )

    return messages, nicknames


def main():
    """Main function to scrape forum data with browser-identical headers"""
    base_url = "https://www.blast.hk/whats-new/latest-activity"

    print("=== Starting Forum Scraping with Browser Headers ===")

    # Get HTML using browser-identical session
    html = get_html_with_browser_session(base_url)
    if not html:
        print("Failed to get main activity page")
        return

    # Parse activity feed to get thread info
    threads = parse_activity_feed(html)
    print(f"Found {len(threads)} unique threads to process")

    if len(threads) == 0:
        print("ERROR: No threads found!")
        return

    topics_data = {}
    all_messages = []
    all_nicknames = set()

    # Process first 10 threads
    for thread_id, topic_title in threads[:10]:
        last_page_url, actual_title = get_last_page_url(thread_id)
        if last_page_url:
            final_title = (
                actual_title if "BLASTHACK" not in actual_title else topic_title
            )
            print(f"Processing {last_page_url} - {final_title}")
            last_page_html = get_html_with_browser_session(last_page_url)
            if last_page_html:
                messages, nicknames = parse_last_page(last_page_html, final_title)
                all_nicknames.update(nicknames)
                all_messages.extend(messages)

                if final_title not in topics_data:
                    topics_data[final_title] = {"messages": []}
                topics_data[final_title]["messages"].extend(messages)

    # Load stopwords (if file exists)
    stopwords_path = os.path.join(os.path.dirname(__file__), "stopwords.json")
    stopwords = []
    if os.path.exists(stopwords_path):
        with open(stopwords_path, "r", encoding="utf-8") as f:
            stopwords = json.load(f)

    excluded_words = set(stopwords) | all_nicknames

    total_messages = 0
    for title, data in topics_data.items():
        data["total_messages"] = len(data["messages"])
        total_messages += data["total_messages"]

    word_counts = Counter()
    for msg in all_messages:
        full_text = "".join(
            [part["content"] for part in msg["text"] if part["type"] == "text"]
        )
        words = re.findall(r"\b[a-zA-Zа-яА-Я]+\b", full_text.lower())
        word_counts.update([word for word in words if word not in excluded_words])

    output_data = {
        "topics": topics_data,
        "top_10_words": word_counts.most_common(10),
        "total_messages": total_messages,
        "total_threads": len(topics_data),
    }

    with open("forum_data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)

    print(f"\n=== SCRAPING COMPLETE ===")
    print(f"Total threads processed: {len(topics_data)}")
    print(f"Total messages extracted: {total_messages}")
    print("Data saved to forum_data.json")


if __name__ == "__main__":
    main()
