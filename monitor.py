import os
import re
import time
import subprocess
from datetime import datetime

import requests
from bs4 import BeautifulSoup


GALLERY_URL = "https://gall.dcinside.com/mgallery/board/lists/?id=minikeyboard"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK"]

STATE_FILE = "last_post.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    )
}


def get_latest_posts():
    response = requests.get(
        GALLERY_URL,
        headers=HEADERS,
        timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    posts = []

    for row in soup.select("tr.ub-content"):
        num_element = row.select_one(".gall_num")

        if not num_element:
            continue

        num_text = num_element.get_text(strip=True)

        # 공지/광고 등 숫자가 아닌 게시물은 제외
        if not num_text.isdigit():
            continue

        post_number = int(num_text)

        title_element = row.select_one(".gall_tit a")
        author_element = row.select_one(".gall_writer")
        date_element = row.select_one(".gall_date")

        if not title_element:
            continue

        title = title_element.get_text(" ", strip=True)

        author = (
            author_element.get_text(" ", strip=True)
            if author_element
            else "알 수 없음"
        )

        # 작성자 정보에 불필요한 내용이 붙는 경우 정리
        author = re.sub(r"\s+", " ", author).strip()

        post_time = (
            date_element.get_text(" ", strip=True)
            if date_element
            else "알 수 없음"
        )

        posts.append({
            "number": post_number,
            "title": title,
            "author": author,
            "time": post_time,
        })

    posts.sort(key=lambda x: x["number"])

    return posts


def load_last_post():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def save_last_post(post_number):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(str(post_number))


def send_discord(post):
    content = (
        "🔔 **새 글 등록**\n\n"
        f"**제목:** {post['title']}\n"
        f"**작성자:** {post['author']}\n"
        f"**시간:** {post['time']}"
    )

    response = requests.post(
        WEBHOOK_URL,
        json={"content": content},
        timeout=20
    )

    response.raise_for_status()


def git_save_state():
    try:
        subprocess.run(
            ["git", "config", "user.name", "dcinside-notifier"],
            check=True
        )

        subprocess.run(
            ["git", "config", "user.email", "actions@github.com"],
            check=True
        )

        subprocess.run(
            ["git", "add", STATE_FILE],
            check=True
        )

        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"]
        )

        # 변경사항이 있을 때만 commit
        if result.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", "Update last post state"],
                check=True
            )

            subprocess.run(
                ["git", "push"],
                check=True
            )

    except Exception as e:
        print(f"State save error: {e}")


def check_once():
    posts = get_latest_posts()

    if not posts:
        print("게시글을 찾지 못했습니다.")
        return

    last_post = load_last_post()

    print(f"현재 최신 게시글: {posts[-1]['number']}")
    print(f"저장된 마지막 게시글: {last_post}")

    # 최초 실행
    if last_post is None:
        latest_number = posts[-1]["number"]
        save_last_post(latest_number)
        git_save_state()

        print(
            f"최초 실행이므로 {latest_number}번을 기준점으로 저장했습니다."
        )
        return

    new_posts = [
        post
        for post in posts
        if post["number"] > last_post
    ]

    if not new_posts:
        print("새 글이 없습니다.")
        return

    for post in new_posts:
        print(
            f"새 글 발견: {post['number']} / "
            f"{post['title']}"
        )

        try:
            send_discord(post)
            print("Discord 전송 성공")

            # 성공적으로 전송한 글만 상태 저장
            save_last_post(post["number"])
            git_save_state()

        except Exception as e:
            print(f"Discord 전송 실패: {e}")
            break


def main():
    # 약 4분 30초 동안 1분 간격으로 감시
    end_time = time.time() + (4 * 60 + 30)

    while time.time() < end_time:
        try:
            check_once()
        except Exception as e:
            print(f"오류 발생: {e}")

        remaining = end_time - time.time()

        if remaining <= 0:
            break

        sleep_time = min(60, remaining)
        print(f"{int(sleep_time)}초 후 다시 확인합니다.")
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
