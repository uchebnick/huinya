from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, Enum, Date, DateTime, Text
from sqlalchemy.orm import relationship, declarative_base
import enum
from datetime import datetime

Base = declarative_base()


class DishType(str, enum.Enum):
    MAIN = "MAIN"
    GARNISH = "GARNISH"
    PREPARED = "PREPARED"
    DRINK = "DRINK"
    SALAD = "SALAD"
    SOUP = "SOUP"
    BREAD = "BREAD"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    PROBLEM = "PROBLEM"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    secondary_name = Column(String)
    email = Column(String, unique=True, index=True)
    status = Column(String)
    is_admin = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)
    verification_code = Column(String, nullable=True)

    orders = relationship("Order", back_populates="user")


class Dish(Base):
    __tablename__ = "dishes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    short_name = Column(String, nullable=True)
    type = Column(Enum(DishType))
    composition = Column(String)
    quantity_grams = Column(Integer)
    price_rub = Column(Float)
    is_provider = Column(Boolean, default=True)


class ModuleMenu(Base):
    __tablename__ = "module_menu"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer)
    dish_id = Column(Integer, ForeignKey("dishes.id"))

    dish = relationship("Dish")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    week_start_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)

    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    total_amount = Column(Float, default=0.0)
    payment_proof_path = Column(String, nullable=True)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    dish_id = Column(Integer, ForeignKey("dishes.id"))
    day_of_week = Column(Integer)  # 0-6
    quantity = Column(Integer)

    order = relationship("Order", back_populates="items")
    dish = relationship("Dish")