"""Migration of farmer profile (Gen1, Odoo g2p_ati) records into the Farmer registry.

source     reads the Odoo database
codes      Odoo values to registry codes
geo        Odoo locations to the country pack's P-codes and hierarchy
transform  Odoo records to registry rows, with the problems found (no I/O)
load       writes the rows through the registry's own models
"""
