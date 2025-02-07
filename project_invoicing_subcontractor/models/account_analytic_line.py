# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, exceptions, fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    subcontractor_work_id = fields.Many2one("subcontractor.work")
    invoice_line_id = fields.Many2one(
        "account.move.line",
        compute="_compute_invoice_line",
        store=True,
    )
    invoice_id = fields.Many2one(
        "account.move",
        related="invoice_line_id.move_id",
        store=True,
    )
    supplier_invoice_line_id = fields.Many2one("account.move.line")
    task_stage_id = fields.Many2one(
        "project.task.type", related="task_id.stage_id", store=True
    )
    invoiceable = fields.Boolean(compute="_compute_invoiceable", store=True)
    discount = fields.Float(digits="Discount", default=0)
    invoiceable_amount = fields.Float(compute="_compute_invoiceable_amount", store=True)
    date_invoiceable = fields.Date(compute="_compute_date_invoiceable", store=True)

    @api.depends("subcontractor_work_id", "supplier_invoice_line_id")
    def _compute_invoice_line(self):
        for record in self:
            record.invoice_line_id = (
                record.subcontractor_work_id.invoice_line_id
                or record.supplier_invoice_line_id
            )

    @api.depends("invoiceable", "task_id.timesheet_ids", "task_id.invoicing")
    def _compute_date_invoiceable(self):
        for record in self:
            if record.task_id.invoicing == "progressive":
                record.date_invoiceable = record.date
            elif record.invoiceable:
                record.date_invoiceable = max(
                    record.task_id.mapped("timesheet_ids.date")
                )
            else:
                record.date_invoiceable = None

    def write(self, vals):
        if vals.get("subcontractor_work_id"):
            already_invoiced = self.filtered(lambda aal: aal.subcontractor_work_id)
            if already_invoiced:
                raise exceptions.UserError_(
                    "You can't invoice timesheets %s, it has already been invoiced"
                    % already_invoiced.ids
                )
        return super().write(vals)

    def is_invoiceable(self):
        self.ensure_one()
        invoicing = self.task_id.invoicing
        if self.discount == 100:
            return False
        elif invoicing == "progressive":
            return True
        elif invoicing == "none":
            return False
        elif invoicing == "finished":
            return self.task_stage_id == self.project_id.invoicing_stage_id

    @api.depends(
        "discount",
        "task_id.stage_id",
        "task_id.invoicing",
        "project_id.invoicing_stage_id",
    )
    def _compute_invoiceable(self):
        for record in self:
            record.invoiceable = record.is_invoiceable()

    def _get_invoiceable_qty_with_project_unit(self, project=False):
        project = project or self.mapped("project_id")
        project.ensure_one()
        return self._get_invoiceable_qty_with_unit(project.uom_id)

    @api.depends("discount", "unit_amount")
    def _compute_invoiceable_amount(self):
        for record in self:
            record.invoiceable_amount = record.unit_amount * (
                1 - record.discount / 100.0
            )

    def _get_invoiceable_qty_with_unit(self, uom):
        if not self:
            return 0
        hours_uom = self.env.ref("uom.product_uom_hour")
        days_uom = self.env.ref("uom.product_uom_day")
        if uom == hours_uom:
            return sum(self.mapped("invoiceable_amount"))
        elif uom == days_uom:
            project = self.mapped("project_id")
            project.ensure_one()
            return project.convert_hours_to_days(sum(self.mapped("invoiceable_amount")))
        else:
            # TODO see if we have the case
            raise NotImplementedError
