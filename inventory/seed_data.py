"""
Seed inventory data: categories + sample items
Run: python manage.py shell < inventory/seed_data.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from inventory.models import Category, InventoryItem
from finance.models import Account

# Find GL accounts
inv_account = Account.objects.filter(sub_type='INVENTORY').first()
expense_accounts = list(Account.objects.filter(type='EXPENSE')[:5])

print("Inventory GL account:", inv_account)
print("Expense accounts:", [a.code for a in expense_accounts])

# Categories
categories_data = [
    {'name': 'Stationery', 'code': 'STAT', 'description': 'Office stationery and writing materials'},
    {'name': 'Cleaning Supplies', 'code': 'CLN', 'description': 'Cleaning materials and consumables'},
    {'name': 'Electronics', 'code': 'ELEC', 'description': 'Electronic equipment and accessories'},
    {'name': 'Science Lab', 'code': 'LAB', 'description': 'Laboratory chemicals, equipment and consumables'},
    {'name': 'Office Equipment', 'code': 'OFFC', 'description': 'Office furniture and equipment'},
    {'name': 'Sports Equipment', 'code': 'SPRT', 'description': 'Sports and PE equipment'},
    {'name': 'IT Equipment', 'code': 'IT', 'description': 'Computers, peripherals and networking'},
    {'name': 'Maintenance', 'code': 'MAINT', 'description': 'Building maintenance supplies'},
]

created_cats = []
for cat_data in categories_data:
    # Assign GL expense account to categories
    gl = expense_accounts[0] if expense_accounts else None
    cat, created = Category.objects.get_or_create(
        code=cat_data['code'],
        defaults={
            'name': cat_data['name'],
            'description': cat_data['description'],
            'gl_expense_account': gl
        }
    )
    created_cats.append(cat)
    print(f"{'Created' if created else 'Exists'}: {cat.name}")

# Sample items
items_data = [
    {'name': 'A4 Paper (Ream)', 'category': 'STAT', 'unit_of_measure': 'Ream', 'unit_cost': '450.00', 'stock_quantity': 200, 'min_level': 50, 'reorder_quantity': 80},
    {'name': 'Ballpoint Pens (Blue)', 'category': 'STAT', 'unit_of_measure': 'Box', 'unit_cost': '350.00', 'stock_quantity': 100, 'min_level': 20, 'reorder_quantity': 40},
    {'name': 'Whiteboard Markers', 'category': 'STAT', 'unit_of_measure': 'Box', 'unit_cost': '800.00', 'stock_quantity': 45, 'min_level': 10, 'reorder_quantity': 20},
    {'name': 'Exercise Books (96pg)', 'category': 'STAT', 'unit_of_measure': 'Pack', 'unit_cost': '1200.00', 'stock_quantity': 500, 'min_level': 100, 'reorder_quantity': 200},
    {'name': 'Floor Detergent (5L)', 'category': 'CLN', 'unit_of_measure': 'Bottle', 'unit_cost': '650.00', 'stock_quantity': 30, 'min_level': 10, 'reorder_quantity': 15},
    {'name': 'Hand Soap (5L)', 'category': 'CLN', 'unit_of_measure': 'Bottle', 'unit_cost': '450.00', 'stock_quantity': 25, 'min_level': 8, 'reorder_quantity': 12},
    {'name': 'Toilet Paper (Pack 48)', 'category': 'CLN', 'unit_of_measure': 'Pack', 'unit_cost': '2400.00', 'stock_quantity': 15, 'min_level': 5, 'reorder_quantity': 8},
    {'name': 'Scientific Calculator', 'category': 'ELEC', 'unit_of_measure': 'Pcs', 'unit_cost': '2500.00', 'stock_quantity': 60, 'min_level': 10, 'reorder_quantity': 20, 'item_type': 'CAPITAL_ASSET'},
    {'name': 'Projector Lamp', 'category': 'ELEC', 'unit_of_measure': 'Pcs', 'unit_cost': '8500.00', 'stock_quantity': 5, 'min_level': 2, 'reorder_quantity': 3},
    {'name': 'Bunsen Burner', 'category': 'LAB', 'unit_of_measure': 'Pcs', 'unit_cost': '3200.00', 'stock_quantity': 20, 'min_level': 5, 'reorder_quantity': 8, 'item_type': 'CAPITAL_ASSET'},
    {'name': 'Test Tubes (Box 50)', 'category': 'LAB', 'unit_of_measure': 'Box', 'unit_cost': '1500.00', 'stock_quantity': 12, 'min_level': 3, 'reorder_quantity': 5},
    {'name': 'Office Chair', 'category': 'OFFC', 'unit_of_measure': 'Pcs', 'unit_cost': '12000.00', 'stock_quantity': 8, 'min_level': 2, 'reorder_quantity': 4, 'item_type': 'CAPITAL_ASSET'},
    {'name': 'Printer Toner (HP)', 'category': 'OFFC', 'unit_of_measure': 'Pcs', 'unit_cost': '4500.00', 'stock_quantity': 10, 'min_level': 3, 'reorder_quantity': 5},
    {'name': 'Footballs', 'category': 'SPRT', 'unit_of_measure': 'Pcs', 'unit_cost': '3500.00', 'stock_quantity': 15, 'min_level': 5, 'reorder_quantity': 8},
    {'name': 'Network Cable (100m)', 'category': 'IT', 'unit_of_measure': 'Roll', 'unit_cost': '2800.00', 'stock_quantity': 5, 'min_level': 2, 'reorder_quantity': 3},
    {'name': 'Paint - White (20L)', 'category': 'MAINT', 'unit_of_measure': 'Jerrican', 'unit_cost': '5500.00', 'stock_quantity': 4, 'min_level': 2, 'reorder_quantity': 3},
]

for item_data in items_data:
    cat_code = item_data.pop('category')
    cat = Category.objects.get(code=cat_code)
    item_type = item_data.pop('item_type', 'CONSUMABLE')
    
    item, created = InventoryItem.objects.get_or_create(
        name=item_data['name'],
        defaults={
            'category': cat,
            'item_type': item_type,
            'unit_of_measure': item_data['unit_of_measure'],
            'unit_cost': item_data['unit_cost'],
            'stock_quantity': item_data['stock_quantity'],
            'min_level': item_data['min_level'],
            'reorder_quantity': item_data['reorder_quantity'],
            'gl_asset_account': inv_account,
            'gl_expense_account': expense_accounts[0] if expense_accounts else None,
            'location': 'Main Store',
        }
    )
    print(f"{'Created' if created else 'Exists'}: {item.code} - {item.name} (Qty: {item.stock_quantity})")

print(f"\nDone! {Category.objects.count()} categories, {InventoryItem.objects.count()} items")
