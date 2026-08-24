import os
import re
import time
import subprocess

import requests
from bs4 import BeautifulSoup


# ============================================================
# 설정
# ============================================================

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


# ============================================================
# 디시인사이드 게시글 가져오기
# ============================================================

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

        # 게시글 번호
        num_element = row.select_one(".gall_num")

        if not num_element:
            continue

        num_text = num_element.get_text(strip=True)

        # 공지/광고 등 숫자가 아닌 항목 제외
        if not num_text.isdigit():
            continue

        post_number = int(num_text)

        # 제목
        title_element = row.select_one(".gall_tit a")

        if not title_element:
            continue

        title = title_element.get_text(" ", strip=True)

        # 작성자
        author_element = row.select_one(".gall_writer")

        if author_element:
            author = author_element.get_text(" ", strip=True)
        else:
            author = "알 수 없음"

        # 공백 정리
        author = re.sub(r"\s+", " ", author).strip()

        # 작성 시간
        date_element = row.select_one(".gall_date")

        if date_element:
            post_time = date_element.get_text(" ", strip=True)
        else:
            post_time = "알 수 없음"

        posts.append({
            "number": post_number,
            "title": title,
            "author": author,
            "time": post_time,
        })

    # 게시글 번호 순으로 정렬
    posts.sort(key=lambda x: x["number"])

    return posts


# ============================================================
# 마지막으로 확인한 게시글 번호 읽기
# ============================================================

def load_last_post():

    if not os.path.exists(STATE_FILE):
        return None

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return int(f.read().strip())

    except Exception:

        return None


# ============================================================
# 마지막 게시글 번호 저장
# ============================================================

def save_last_post(post_number):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(str(post_number))


# ============================================================
# Discord Webhook 전송
# ============================================================

def send_discord(post):

    content = (
        "🔔 **새 글 등록**\n\n"
        f"**제목:** {post['title']}\n"
        f"**작성자:** {post['author']}\n"
        f"**시간:** {post['time']}"
    )

    response = requests.post(
        WEBHOOK_URL,
        json={
            "content": content
        },
        timeout=20
    )

    response.raise_for_status()


# ============================================================
# GitHub에 마지막 게시글 번호 저장
# ============================================================

def git_save_state():

    try:

        # ----------------------------------------------------
        # Git 사용자 설정
        # ----------------------------------------------------

        subprocess.run(
            [
                "git",
                "config",
                "user.name",
                "dcinside-notifier"
            ],
            check=True
        )

        subprocess.run(
            [
                "git",
                "config",
                "user.email",
                "actions@github.com"
            ],
            check=True
        )

        # ----------------------------------------------------
        # 원격 저장소의 최신 상태 확인
        # ----------------------------------------------------

        subprocess.run(
            [
                "git",
                "fetch",
                "origin",
                "main"
            ],
            check=True
        )

        # ----------------------------------------------------
        # 현재 변경된 last_post.txt 임시 보관
        #
        # 최초 실행에서는 last_post.txt가 새 파일이므로
        # -u 옵션으로 untracked 파일도 stash에 포함
        # ----------------------------------------------------

        stash_result = subprocess.run(
            [
                "git",
                "stash",
                "push",
                "-u",
                "-m",
                "temporary last post state",
                "--",
                STATE_FILE
            ],
            capture_output=True,
            text=True
        )

        stash_created = (
            "No local changes" not in stash_result.stdout
        )

        # ----------------------------------------------------
        # 원격 main의 최신 변경사항 반영
        # ----------------------------------------------------

        subprocess.run(
    [
        "git",
        "pull",
        "--rebase",
        "origin",
        "main"
    ],
    check=True
)

        # ----------------------------------------------------
        # 임시 보관했던 last_post.txt 복원
        # ----------------------------------------------------

        if stash_created:

            subprocess.run(
                [
                    "git",
                    "stash",
                    "pop"
                ],
                check=True
            )

        # ----------------------------------------------------
        # 상태 파일 추가
        # ----------------------------------------------------

        subprocess.run(
            [
                "git",
                "add",
                STATE_FILE
            ],
            check=True
        )

        # ----------------------------------------------------
        # 변경사항 확인
        # ----------------------------------------------------

        result = subprocess.run(
            [
                "git",
                "diff",
                "--cached",
                "--quiet"
            ]
        )

        # 변경사항이 없으면 종료
        if result.returncode == 0:

            print(
                "저장할 상태 변경사항이 없습니다."
            )

            return

        # ----------------------------------------------------
        # 커밋
        # ----------------------------------------------------

        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Update last post state"
            ],
            check=True
        )

        # ----------------------------------------------------
        # GitHub에 push
        # 최대 3번 시도
        # ----------------------------------------------------

        for attempt in range(1, 4):

            try:

                subprocess.run(
                    [
                        "git",
                        "push",
                        "origin",
                        "main"
                    ],
                    check=True
                )

                print(
                    "마지막 게시글 상태 저장 성공 "
                    f"(시도 {attempt}/3)"
                )

                return

            except subprocess.CalledProcessError:

                if attempt == 3:
                    raise

                print(
                    "Push 실패. "
                    "원격 저장소를 다시 확인합니다. "
                    f"({attempt}/3)"
                )

                subprocess.run(
                    [
                        "git",
                        "pull",
                        "--rebase",
                        "origin",
                        "main"
                    ],
                    check=True
                )

        raise RuntimeError(
            "GitHub에 마지막 게시글 상태를 저장하지 못했습니다."
        )

    except Exception as e:

        print(
            f"State save error: {e}"
        )

        # 상태 저장 실패를 Actions에서도 실패로 표시
        raise


# ============================================================
# 한 번의 게시글 확인
# ============================================================

def check_once():

    posts = get_latest_posts()

    if not posts:

        print(
            "게시글을 찾지 못했습니다."
        )

        return

    last_post = load_last_post()

    print(
        f"현재 최신 게시글: "
        f"{posts[-1]['number']}"
    )

    print(
        f"저장된 마지막 게시글: "
        f"{last_post}"
    )

    # --------------------------------------------------------
    # 최초 실행
    # --------------------------------------------------------

    if last_post is None:

        latest_number = posts[-1]["number"]

        save_last_post(
            latest_number
        )

        git_save_state()

        print(
            f"최초 실행이므로 "
            f"{latest_number}번을 "
            f"기준점으로 저장했습니다."
        )

        return

    # --------------------------------------------------------
    # 새 게시글 찾기
    # --------------------------------------------------------

    new_posts = [
        post
        for post in posts
        if post["number"] > last_post
    ]

    if not new_posts:

        print(
            "새 글이 없습니다."
        )

        return

    # --------------------------------------------------------
    # 새 게시글 처리
    # --------------------------------------------------------

    for post in new_posts:

        print(
            f"새 글 발견: "
            f"{post['number']} / "
            f"{post['title']}"
        )

        try:

            # Discord 전송
            send_discord(post)

            print(
                "Discord 전송 성공"
            )

            # Discord 전송에 성공한 경우에만
            # 마지막 게시글 번호 업데이트
            save_last_post(
                post["number"]
            )

            # GitHub에 상태 저장
            git_save_state()

        except Exception as e:

            print(
                f"게시글 "
                f"{post['number']} "
                f"처리 실패: {e}"
            )

            # 실패한 글 이후의 게시글은
            # 다음 실행에서 다시 처리
            break


# ============================================================
# 메인 감시 루프
# ============================================================

def main():

    # 한 번 실행될 때 약 4분 30초 동안 감시
    #
    # GitHub Actions가 5분마다 새 실행을 시작하므로
    # 사실상 약 1분 간격으로 감시하는 구조
    # ========================================================

    end_time = (
        time.time()
        + (4 * 60 + 30)
    )

    while time.time() < end_time:

        try:

            check_once()

        except Exception as e:

            print(
                f"오류 발생: {e}"
            )

        # 다음 확인까지 남은 시간
        remaining = (
            end_time
            - time.time()
        )

        if remaining <= 0:

            break

        # 최대 60초 대기
        sleep_time = min(
            60,
            remaining
        )

        print(
            f"{int(sleep_time)}초 후 "
            "다시 확인합니다."
        )

        time.sleep(
            sleep_time
        )

    print(
        "이번 감시 작업을 종료합니다."
    )


# ============================================================
# 프로그램 시작
# ============================================================

if __name__ == "__main__":

    main()
