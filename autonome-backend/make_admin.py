import sys
from sqlmodel import Session, select
from app.core.database import engine
from app.models.domain import User


def make_superuser(email: str):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        if not user:
            print(f"❌ 错误：未找到邮箱为 {email} 的用户，请先去前端注册。")
            return
            
        user.is_superuser = True
        session.add(user)
        session.commit()
        print(f"🎉 成功！用户 {email} 已被提升为超级管理员 (Superuser)！")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python make_admin.py <用户邮箱>")
    else:
        make_superuser(sys.argv[1])
