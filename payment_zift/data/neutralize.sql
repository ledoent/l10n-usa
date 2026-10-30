-- Copyright 2026 Ledo Enterprises
-- License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
-- disable zift payment provider
UPDATE payment_provider
   SET zift_username = NULL,
       zift_password = NULL,
       zift_account_id = NULL;
