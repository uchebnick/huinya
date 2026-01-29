import random
import string
import os
import csv
import io
from datetime import date
from typing import List, Dict

from dotenv import load_dotenv

from fastapi.responses import FileResponse, StreamingResponse

load_dotenv()

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from auth import JWTAuthMiddleware, create_access_token, require_admin, get_current_user_id
from menu_parser import parse_menu_text
from models import (
    Dish, DishType, User, ModuleMenu, Order, OrderItem, OrderStatus,
    Base
)
from schemas import (
    DishCreate, DishResponse, DishUpdate, RegisterResponse, UserCreate,
    UserResponse, VerifyCodeRequest, VerifyCodeResponse, ResendCodeRequest,
    ResendCodeResponse, AdminUpdateRequest, ModuleMenuRequest,
    OrderCreate, OrderResponse, DishBase
)
import docx_utils

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.security import HTTPBearer


engine = create_engine("sqlite:///./app.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


security_scheme = HTTPBearer(auto_error=False)

app = FastAPI(
    title="Canteen API",
    dependencies=[Depends(security_scheme)]
)
app.add_middleware(JWTAuthMiddleware)



def get_admin_user(request: Request, db: Session = Depends(get_db)) -> User:
    return require_admin(request, db)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    a = request.items()
    print(a)
    user_id = get_current_user_id(request)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def generate_verification_code() -> str:
    return ''.join(random.choices(string.digits, k=6))


def send_verification_email(to_email: str, code: str) -> None:
    print(f"--- EMAIL SIMULATION: Code for {to_email} is {code} ---")
    pass


@app.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing and existing.email_verified:
        raise HTTPException(status_code=400, detail="User exists")

    code = generate_verification_code()
    if existing:
        existing.verification_code = code
        db.commit()
        return RegisterResponse(message="Code resent", user=UserResponse.model_validate(existing))

    new_user = User(
        name=user_data.name,
        secondary_name=user_data.secondary_name,
        email=user_data.email,
        status=user_data.status,
        verification_code=code
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    send_verification_email(new_user.email, code)
    return RegisterResponse(message="Registered", user=UserResponse.model_validate(new_user))

@app.get("/users/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):

    return current_user

@app.post("/verify-code", response_model=VerifyCodeResponse)
def verify_code(data: VerifyCodeRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or user.verification_code != data.code:
        raise HTTPException(status_code=400, detail="Invalid code")

    user.email_verified = True
    user.verification_code = None
    db.commit()
    token = create_access_token(data={"sub": str(user.id)})
    return VerifyCodeResponse(access_token=token, token_type="bearer", user=UserResponse.model_validate(user))



@app.get("/menu", response_model=List[DishResponse])
def get_global_menu(db: Session = Depends(get_db)):
    return db.query(Dish).all()


@app.post("/menu/dish", response_model=DishResponse)
def create_dish(dish: DishCreate, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    new_dish = Dish(**dish.model_dump())
    db.add(new_dish)
    db.commit()
    db.refresh(new_dish)
    return new_dish


@app.post("/menu/upload")
async def upload_menu_file(
    file: UploadFile = File(...),
    is_provider: bool = True,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    content = await file.read()
    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content_str = content.decode("cp1251")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Invalid file encoding. Please use UTF-8.")

    try:
        dishes_data = parse_menu_text(content_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing file: {e}")

    if not dishes_data:
        raise HTTPException(status_code=400, detail="No dishes found in the file.")


    db.query(Dish).filter(Dish.is_provider == is_provider).delete(synchronize_session=False)

    new_dishes = []
    for item in dishes_data:
        dish = Dish(
            name=item.name,
            type=item.type,
            composition=item.composition,
            quantity_grams=item.quantity_grams,
            price_rub=item.price_rub,
            is_provider=is_provider
        )
        db.add(dish)
        new_dishes.append(dish)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    return {
        "message": "Menu updated successfully",
        "deleted_old": True,
        "added_new": len(new_dishes),
        "menu_type": "Provider" if is_provider else "Own Kitchen"
    }



@app.post("/module-menu", status_code=201)
def set_module_menu(
        menu_data: ModuleMenuRequest,
        db: Session = Depends(get_db),
        admin: User = Depends(get_admin_user)
):
    db.query(ModuleMenu).delete()

    for day_entry in menu_data.schedule:
        day_idx = day_entry.day_of_week
        dishes = db.query(Dish).filter(Dish.id.in_(day_entry.dish_ids)).all()

        type_counts = {}
        for d in dishes:
            type_counts[d.type] = type_counts.get(d.type, 0) + 1

        for dtype, count in type_counts.items():
            if count > 2:
                raise HTTPException(
                    status_code=400,
                    detail=f"Day {day_idx}: Too many dishes of type {dtype} (Max 2)"
                )

        for d_id in day_entry.dish_ids:
            mm = ModuleMenu(day_of_week=day_idx, dish_id=d_id)
            db.add(mm)

    db.commit()
    return {"message": "Module menu saved successfully"}


@app.get("/module-menu")
def get_module_menu(db: Session = Depends(get_db)):
    menu_items = db.query(ModuleMenu).all()
    return menu_items



@app.post("/orders", response_model=OrderResponse)
def create_order(
        order_data: OrderCreate,
        request: Request,
        db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    total_price = 0.0
    new_order = Order(
        user_id=user.id,
        week_start_date=order_data.week_start_date,
        status=OrderStatus.PENDING
    )
    db.add(new_order)
    db.flush()

    for day_req in order_data.days:
        for item in day_req.items:
            if item.quantity > 0:
                dish = db.query(Dish).filter(Dish.id == item.dish_id).first()
                if not dish: continue

                cost = dish.price_rub * item.quantity
                total_price += cost

                order_item = OrderItem(
                    order_id=new_order.id,
                    dish_id=dish.id,
                    day_of_week=day_req.day_of_week,
                    quantity=item.quantity
                )
                db.add(order_item)

    new_order.total_amount = total_price
    db.commit()
    db.refresh(new_order)
    return new_order


@app.post("/orders/{order_id}/pay")
async def pay_order(
        order_id: int,
        request: Request,
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    os.makedirs("uploads", exist_ok=True)
    file_location = f"uploads/{order_id}_{file.filename}"
    with open(file_location, "wb+") as file_object:
        file_object.write(await file.read())

    order.payment_proof_path = file_location

    db.commit()
    return {"message": "Payment proof uploaded"}


@app.get("/orders", response_model=List[OrderResponse])
def get_my_orders(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    orders = db.query(Order).filter(Order.user_id == user.id).order_by(Order.id.desc()).all()
    return orders


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order_details(order_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order


@app.patch("/admin/orders/{order_id}/status")
def update_order_status(
        order_id: int,
        status: OrderStatus,
        db: Session = Depends(get_db),
        admin: User = Depends(get_admin_user)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order: raise HTTPException(404, "Order not found")
    order.status = status
    db.commit()
    return {"message": f"Order marked as {status}"}


@app.get("/admin/reports/docx")
def download_table_report(date_query: date, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    day_idx = date_query.weekday()

    items = db.query(OrderItem).join(Order).join(User).join(Dish) \
        .filter(OrderItem.day_of_week == day_idx) \
        .filter(Order.status == OrderStatus.PAID) \
        .all()

    user_map = {}
    for it in items:
        uid = it.order.user_id
        if uid not in user_map:
            user_map[uid] = {
                "user_name": f"{it.order.user.name} {it.order.user.secondary_name}",
                "user_class": it.order.user.status,
                "dishes": []
            }

        d_name = it.dish.short_name if it.dish.short_name else it.dish.name

        for _ in range(it.quantity):
            user_map[uid]["dishes"].append(d_name)

    report_data = list(user_map.values())

    path = docx_utils.generate_table_setting_report(report_data, filename=f"Report_{date_query}.docx")

    return FileResponse(path, filename=f"Table_Report_{date_query}.docx")

@app.get("/module-menu/export")
def export_module_menu(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    menu_items = db.query(ModuleMenu).join(Dish).order_by(ModuleMenu.day_of_week).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Day', 'Dish Name', 'Type', 'Grams', 'Price'])

    days_map = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    for item in menu_items:
        writer.writerow([
            days_map[item.day_of_week],
            item.dish.name,
            item.dish.type,
            item.dish.quantity_grams,
            item.dish.price_rub
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=module_menu.csv"}
    )


@app.get("/admin/reports/summary")
def get_summary_report(date_query: date, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):

    day_idx = date_query.weekday()


    stats = db.query(
        Dish.name,
        func.sum(OrderItem.quantity).label("total_qty"),
        func.sum(OrderItem.quantity * Dish.price_rub).label("total_revenue")
    ).join(OrderItem, OrderItem.dish_id == Dish.id) \
        .join(Order, OrderItem.order_id == Order.id) \
        .filter(OrderItem.day_of_week == day_idx) \
        .filter(Order.status == OrderStatus.PAID) \
        .group_by(Dish.id).all()

    total_day_revenue = sum(s.total_revenue for s in stats) if stats else 0

    return {
        "date": date_query,
        "total_revenue": total_day_revenue,
        "items": [
            {
                "dish": s.name,
                "count": s.total_qty,
                "revenue": s.total_revenue
            }
            for s in stats
        ]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)