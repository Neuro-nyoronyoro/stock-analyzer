import hashlib
import secrets
from datetime import datetime, timedelta
from db.database import get_session, User


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    return f"{salt}:{_hash_password(password, salt)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, pw_hash = stored_hash.split(":", 1)
        return _hash_password(password, salt) == pw_hash
    except Exception:
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def register_user(email: str, password: str, display_name: str):
    """ユーザー登録。成功時は (user, token)、失敗時は (None, error_msg) を返す。
    未認証アカウントが残っている場合は新トークンを発行して再送できるようにする。"""
    s = get_session()
    try:
        existing = s.query(User).filter_by(email=email).first()
        if existing:
            if existing.is_verified:
                return None, "このメールアドレスは既に登録されています"
            # 未認証アカウントが残っている場合：情報を更新してトークンを新規発行
            token = generate_token()
            existing.display_name = display_name
            existing.password_hash = hash_password(password)
            existing.verification_token = token
            s.commit()
            user_data = {"id": existing.id, "email": existing.email, "display_name": existing.display_name}
            return user_data, token
        is_first = s.query(User).count() == 0
        token = generate_token()
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            is_verified=False,
            is_approved=is_first,
            is_admin=is_first,
            verification_token=token,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        user_data = {"id": user.id, "email": user.email, "display_name": user.display_name}
        return user_data, token
    except Exception as e:
        s.rollback()
        return None, str(e)
    finally:
        s.close()


def verify_email(token: str) -> bool:
    import sys
    token = token.strip()
    s = get_session()
    try:
        user = s.query(User).filter_by(verification_token=token).first()
        if not user:
            all_users = s.query(User).all()
            print(f"[verify_email] FAIL: token='{token}' not found in DB", file=sys.stderr, flush=True)
            for u in all_users:
                print(f"[verify_email]   id={u.id} email={u.email} stored_token={repr(u.verification_token)}", file=sys.stderr, flush=True)
            return False
        user.is_verified = True
        user.verification_token = None
        s.commit()
        print(f"[verify_email] OK: email={user.email}", file=sys.stderr, flush=True)
        return True
    except Exception as e:
        print(f"[verify_email] EXCEPTION: {e}", file=sys.stderr, flush=True)
        s.rollback()
        return False
    finally:
        s.close()


def login(email: str, password: str):
    """ログイン。成功時は (user_dict, None)、失敗時は (None, error_msg) を返す"""
    s = get_session()
    try:
        user = s.query(User).filter_by(email=email).first()
        if not user or not verify_password(password, user.password_hash):
            return None, "メールアドレスまたはパスワードが正しくありません"
        if not user.is_verified:
            return None, "メールアドレスの確認が完了していません。確認メールをご確認ください"
        if not user.is_approved:
            return None, "アカウントは管理者の承認待ちです。しばらくお待ちください"
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
        }, None
    finally:
        s.close()


def create_reset_token(email: str):
    """パスワードリセット用トークンを生成。ユーザーが存在しない場合も同じ戻り値で列挙攻撃を防ぐ"""
    s = get_session()
    try:
        user = s.query(User).filter_by(email=email).first()
        if not user:
            return None, None
        token = generate_token()
        user.reset_token = token
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        s.commit()
        return {"email": user.email, "display_name": user.display_name}, token
    except Exception:
        s.rollback()
        return None, None
    finally:
        s.close()


def reset_password(token: str, new_password: str) -> bool:
    s = get_session()
    try:
        user = s.query(User).filter_by(reset_token=token).first()
        if not user or not user.reset_token_expires:
            return False
        if user.reset_token_expires < datetime.utcnow():
            return False
        user.password_hash = hash_password(new_password)
        user.reset_token = None
        user.reset_token_expires = None
        s.commit()
        return True
    except Exception:
        s.rollback()
        return False
    finally:
        s.close()


def update_profile(user_id: int, display_name: str = None, email: str = None):
    """プロフィール更新。成功時は True、失敗時は (False, error_msg)"""
    s = get_session()
    try:
        user = s.query(User).filter_by(id=user_id).first()
        if not user:
            return False, "ユーザーが見つかりません"
        if display_name:
            user.display_name = display_name
        if email and email != user.email:
            if s.query(User).filter_by(email=email).first():
                return False, "このメールアドレスは既に使用されています"
            user.email = email
        s.commit()
        return True, None
    except Exception as e:
        s.rollback()
        return False, str(e)
    finally:
        s.close()


def change_password(user_id: int, current_password: str, new_password: str):
    s = get_session()
    try:
        user = s.query(User).filter_by(id=user_id).first()
        if not user or not verify_password(current_password, user.password_hash):
            return False, "現在のパスワードが正しくありません"
        user.password_hash = hash_password(new_password)
        s.commit()
        return True, None
    except Exception as e:
        s.rollback()
        return False, str(e)
    finally:
        s.close()
