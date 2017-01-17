# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals

import frappe
import unittest

from frappe.test_runner import make_test_records
from erpnext.exceptions import PartyFrozen, PartyDisabled
from frappe.utils import flt
from erpnext.selling.doctype.customer.customer import get_credit_limit, get_customer_outstanding
from erpnext.tests.utils import create_test_contact_and_address

test_ignore = ["Price List"]

test_records = frappe.get_test_records('Customer')

class TestCustomer(unittest.TestCase):
	def setUp(self):
		if not frappe.get_value('Item', '_Test Item'):
			make_test_records('Item')

	def tearDown(self):
		frappe.db.set_value("Customer", '_Test Customer', 'credit_limit', 0.0)

	def test_party_details(self):
		from erpnext.accounts.party import get_party_details

		frappe.db.sql('delete from tabContact')
		frappe.db.sql('delete from tabAddress')
		frappe.db.sql('delete from `tabDynamic Link`')


		to_check = {
			'selling_price_list': None,
			'customer_group': '_Test Customer Group',
			'contact_designation': None,
			'customer_address': '_Test Address for Customer-Office',
			'contact_department': None,
			'contact_email': 'test_contact_customer@example.com',
			'contact_mobile': None,
			'sales_team': [],
			'contact_display': '_Test Contact for _Test Customer',
			'contact_person': '_Test Contact for _Test Customer-_Test Customer',
			'territory': u'_Test Territory',
			'contact_phone': '+91 0000000000',
			'customer_name': '_Test Customer'
		}

		create_test_contact_and_address()

		frappe.db.set_value("Contact", "_Test Contact for _Test Customer-_Test Customer",
			"is_primary_contact", 1)

		details = get_party_details("_Test Customer")

		for key, value in to_check.iteritems():
			self.assertEquals(value, details.get(key))

	def test_rename(self):
		for name in ("_Test Customer 1", "_Test Customer 1 Renamed"):
			frappe.db.sql("""delete from `tabCommunication`
				where communication_type='Comment' and reference_doctype=%s and reference_name=%s""",
				("Customer", name))

		comment = frappe.get_doc("Customer", "_Test Customer 1").add_comment("Comment", "Test Comment for Rename")

		frappe.rename_doc("Customer", "_Test Customer 1", "_Test Customer 1 Renamed")

		self.assertTrue(frappe.db.exists("Customer", "_Test Customer 1 Renamed"))
		self.assertFalse(frappe.db.exists("Customer", "_Test Customer 1"))

		# test that comment gets renamed
		self.assertEquals(frappe.db.get_value("Communication", {
			"communication_type": "Comment",
			"reference_doctype": "Customer",
			"reference_name": "_Test Customer 1 Renamed"
		}), comment.name)

		frappe.rename_doc("Customer", "_Test Customer 1 Renamed", "_Test Customer 1")

	def test_freezed_customer(self):
		make_test_records("Item")

		frappe.db.set_value("Customer", "_Test Customer", "is_frozen", 1)

		from erpnext.selling.doctype.sales_order.test_sales_order import make_sales_order

		so = make_sales_order(do_not_save= True)

		self.assertRaises(PartyFrozen, so.save)

		frappe.db.set_value("Customer", "_Test Customer", "is_frozen", 0)

		so.save()

	def test_disabled_customer(self):
		make_test_records("Item")

		frappe.db.set_value("Customer", "_Test Customer", "disabled", 1)

		from erpnext.selling.doctype.sales_order.test_sales_order import make_sales_order

		so = make_sales_order(do_not_save=True)

		self.assertRaises(PartyDisabled, so.save)

		frappe.db.set_value("Customer", "_Test Customer", "disabled", 0)

		so.save()

	def test_duplicate_customer(self):
		frappe.db.sql("delete from `tabCustomer` where customer_name='_Test Customer 1'")

		if not frappe.db.get_value("Customer", "_Test Customer 1"):
			test_customer_1 = frappe.get_doc(
				get_customer_dict('_Test Customer 1')).insert(ignore_permissions=True)
		else:
			test_customer_1 = frappe.get_doc("Customer", "_Test Customer 1")

		duplicate_customer = frappe.get_doc(
			get_customer_dict('_Test Customer 1')).insert(ignore_permissions=True)

		self.assertEquals("_Test Customer 1", test_customer_1.name)
		self.assertEquals("_Test Customer 1 - 1", duplicate_customer.name)
		self.assertEquals(test_customer_1.customer_name, duplicate_customer.customer_name)

	def get_customer_outstanding_amount(self):
		from erpnext.selling.doctype.sales_order.test_sales_order import make_sales_order
		outstanding_amt = get_customer_outstanding('_Test Customer', '_Test Company')

		# If outstanding is negative make a transaction to get positive outstanding amount
		if outstanding_amt > 0.0:
			return outstanding_amt

		item_qty = int((abs(outstanding_amt) + 200)/100)
		make_sales_order(qty=item_qty)
		return get_customer_outstanding('_Test Customer', '_Test Company')

	def test_customer_credit_limit(self):
		from erpnext.stock.doctype.delivery_note.test_delivery_note import create_delivery_note
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
		from erpnext.selling.doctype.sales_order.test_sales_order import make_sales_order
		from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

		outstanding_amt = self.get_customer_outstanding_amount()
		credit_limit = get_credit_limit('_Test Customer', '_Test Company')

		if outstanding_amt <= 0.0:
			item_qty = int((abs(outstanding_amt) + 200)/100)
			make_sales_order(qty=item_qty)

		if credit_limit == 0.0:
			frappe.db.set_value("Customer", '_Test Customer', 'credit_limit', outstanding_amt - 50.0)

		# Sales Order
		so = make_sales_order(do_not_submit=True)
		self.assertRaises(frappe.ValidationError, so.submit)

		# Delivery Note
		dn = create_delivery_note(do_not_submit=True)
		self.assertRaises(frappe.ValidationError, dn.submit)

		# Sales Invoice
		si = create_sales_invoice(do_not_submit=True)
		self.assertRaises(frappe.ValidationError, si.submit)

		if credit_limit > outstanding_amt:
			frappe.db.set_value("Customer", '_Test Customer', 'credit_limit', credit_limit)

		# Makes Sales invoice from Sales Order
		so.save(ignore_permissions=True)
		si = make_sales_invoice(so.name)
		si.save(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, make_sales_order)

	def test_customer_credit_limit_on_change(self):
		outstanding_amt = self.get_customer_outstanding_amount()
		customer = frappe.get_doc("Customer", '_Test Customer')
		customer.credit_limit = flt(outstanding_amt - 100)
		self.assertRaises(frappe.ValidationError, customer.save)

def get_customer_dict(customer_name):
	return {
		 "customer_group": "_Test Customer Group",
		 "customer_name": customer_name,
		 "customer_type": "Individual",
		 "doctype": "Customer",
		 "territory": "_Test Territory"
	}
