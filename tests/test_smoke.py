"""Quick smoke test for the package."""
from insurance_product_data_sp import branches, companies, distributors, products

# Test companies
print("Testing companies...")
c = companies.get(company_key="C0737")
print(f"  Company C0737: {c.denomination if c else 'Not found'}")
print(f"  Total companies: {len(companies)}")

# Test distributors
print("Testing distributors...")
print(f"  Total distributors: {len(distributors)}")

# Test branches
print("Testing branches...")
print(f"  Total branches: {len(branches)}")
life = branches.list_life()
print(f"  Life branches: {len(life)}")

# Test products
print("Testing products...")
print(f"  Total products: {len(products)}")
company_prods = products.search_by_company("C0737")
print(f"  Products for C0737: {len(company_prods)}")

print("All tests passed!")
