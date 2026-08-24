import os
import time
import subprocess
import requests
from bs4 import BeautifulSoup


# ============================================================
# 설정
# ============================================================

GALLERY_URL = (
    "https://gall.dcinside.com/mgallery/board/lists/"
    "?id=minikeyboard"
)

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
# 디시인사이드 최신 게시글 가져오기
# ============================================================

def get_latest_posts():

    response = requests.get(
        GALLERY_URL,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    posts = []

    for row in soup.select("tr.ub-content"):

        # --------------------------------------------
        # 게시글 번호
        # --------------------------------------------

        num_element = row.select_one(".gall_num")

        if not num_element:
            continue

        num_text = num_element.get_text(
            strip=True
        )

        # 공지 / 광고 등 숫자가 아닌 항목 제외
        if not num_text.isdigit():
            continue

        post_number = int(num_text)

        # --------------------------------------------
        # 제목
        # --------------------------------------------

        title_element = row.select_one(
            ".gall_tit a"
        )

        if not title_element:
            continue

        title = title_element.get_text(
            " ",
            strip=True
        )

        # --------------------------------------------
        # 작성자
        # --------------------------------------------

        author_element = row.select_one(
            ".gall_writer"
        )

        if author_element:
            author = author_element.get_text(
                " ",
                strip=True
            )
        else:
            author = "알 수 없음"

        # 여러 공백 정리
        author = " ".join(
            author.split()
        )

        # --------------------------------------------
        # 작성 시간
        # --------------------------------------------

        date_element = row.select_one(
            ".gall_date"
        )

        if date_element:
            post_time = date_element.get_text(
                " ",
                strip=True
            )
        else:
            post_time = "알 수 없음"

        posts.append({
            "number": post_number,
            "title": title,
            "author": author,
            "time": post_time
        })

    # 게시글 번호 기준 오름차순 정렬
    posts.sort(
        key=lambda x: x["number"]
    )

    return posts


# ============================================================
# 마지막으로 처리한 게시글 번호 읽기
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

            value = f.read().strip()

        if not value:
            return None

        return int(value)

    except Exception as e:

        print(
            f"마지막 게시글 번호 읽기 실패: {e}"
        )

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

        f.write(
            str(post_number)
        )


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

        # --------------------------------------------
        # Git 사용자 설정
        # --------------------------------------------

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

        # --------------------------------------------
        # 상태 파일 추가
        # --------------------------------------------

        subprocess.run(
            [
                "git",
                "add",
                STATE_FILE
            ],
            check=True
        )

        # --------------------------------------------
        # 변경사항이 있는지 확인
        # --------------------------------------------

        diff_result = subprocess.run(
            [
                "git",
                "diff",
                "--cached",
                "--quiet"
            ]
        )

        if diff_result.returncode == 0:

            print(
                "저장할 상태 변경사항이 없습니다."
            )

            return

        # --------------------------------------------
        # 커밋
        # --------------------------------------------

        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Update last post state"
            ],
            check=True
        )

        # --------------------------------------------
        # 원격 저장소 최신 상태 확인 후 push
        # --------------------------------------------

        for attempt in range(1, 4):

            try:

                print(
                    f"GitHub 저장 시도 "
                    f"({attempt}/3)"
                )

                # 원격 main의 최신 상태 가져오기
                subprocess.run(
                    [
                        "git",
                        "fetch",
                        "origin",
                        "main"
                    ],
                    check=True
                )

                # 현재 커밋을 원격 main 위에 재배치
                subprocess.run(
                    [
                        "git",
                        "rebase",
                        "origin/main"
                    ],
                    check=True
                )

                # push
                subprocess.run(
                    [
                        "git",
                        "push",
                        "origin",
                        "HEAD:main"
                    ],
                    check=True
                )

                print(
                    "마지막 게시글 상태 저장 성공"
                )

                return

            except subprocess.CalledProcessError as e:

                print(
                    f"GitHub 저장 실패 "
                    f"({attempt}/3): {e}"
                )

                # 마지막 시도라면 오류 발생
                if attempt == 3:
                    raise

                # 다음 시도 전 잠시 대기
                time.sleep(3)

    except Exception as e:

        print(
            f"State save error: {e}"
        )

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

    latest_post_number = posts[-1]["number"]

    last_post = load_last_post()

    print(
        f"현재 최신 게시글: "
        f"{latest_post_number}"
    )

    print(
        f"저장된 마지막 게시글: "
        f"{last_post}"
    )

    # ========================================================
    # 최초 실행
    # ========================================================

    if last_post is None:

        save_last_post(
            latest_post_number
        )

        git_save_state()

        print(
            f"최초 실행이므로 "
            f"{latest_post_number}번을 "
            "기준점으로 저장했습니다."
        )

        return

    # ========================================================
    # 새로운 게시글 찾기
    # ========================================================

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

    print(
        f"새 글 {len(new_posts)}개 발견"
    )

    # ========================================================
    # 새 게시글 Discord 전송
    # ========================================================

    last_successful_number = last_post

    for post in new_posts:

        print(
            f"새 글 발견: "
            f"{post['number']} / "
            f"{post['title']}"
        )

        try:

            send_discord(post)

            print(
                f"Discord 전송 성공: "
                f"{post['number']}"
            )

            last_successful_number = (
                post["number"]
            )

        except Exception as e:

            print(
                f"Discord 전송 실패: "
                f"{post['number']} / {e}"
            )

            # 실패한 게시글 이후의 글은
            # 다음 실행에서 다시 처리
            break

    # ========================================================
    # Discord 전송에 성공한 마지막 게시글 저장
    # ========================================================

    if last_successful_number > last_post:

        save_last_post(
            last_successful_number
        )

        git_save_state()

        print(
            f"마지막 처리 게시글: "
            f"{last_successful_number}"
        )


# ============================================================
# 메인 감시 루프
# ============================================================

def main():

    # GitHub Actions 한 번의 실행에서
    # 약 4분 30초 동안 감시
    #
    # workflow가 5분마다 실행되므로
    # 사실상 약 1분 간격으로 계속 확인

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

        # --------------------------------------------
        # 다음 확인까지 최대 60초 대기
        # --------------------------------------------

        remaining = (
            end_time
            - time.time()
        )

        if remaining <= 0:
            break

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
