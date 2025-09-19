import time
from datetime import datetime
from src.data_entry.service.rm_inward_service import RMInwardService
from src.data_entry.models.rm_inward_models import RMInwardIssueRequest

# Data parsed from the user's CSV file.
data_to_migrate = [
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10541', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '815'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10542', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '829'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10543', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '850'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10544', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '837'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10545', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '831'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10546', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '796'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10638', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '668'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10639', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '532'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10640', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '607'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10641', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '160', 'Net wt': '606'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '11323', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C350', 'Coating': 'C3H', 'THK': '0.5', 'SIZE': '380', 'Net wt': '1679'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '11324', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C350', 'Coating': 'C3H', 'THK': '0.5', 'SIZE': '380', 'Net wt': '1680'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '11141', 'Material Sent From': 'Amba Factory', 'MAKE': 'JSW', 'GRADE': '50C350', 'Coating': 'C6L', 'THK': '0.5', 'SIZE': '670', 'Net wt': '3285'},
    {'DATE': '30.04.2025', 'DC CH NO.': 'F/02/25-26', 'Coil No': '10730', 'Material Sent From': 'Amba Factory', 'MAKE': 'Steel Mont', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '5605'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': 'KPS1', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '108', 'Net wt': '525'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': 'KPS2', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '108', 'Net wt': '617'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': 'KPS3', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '108', 'Net wt': '533'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': 'KPS4', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '108', 'Net wt': '407'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': 'KPS5', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '108', 'Net wt': '377'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': 'KPS6', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '108', 'Net wt': '422'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': '3BE600630', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '280', 'Net wt': '1391'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': '3BE600810', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '280', 'Net wt': '1420'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': '41E601726', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '280', 'Net wt': '1346'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': '41E601711', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '280', 'Net wt': '1302'},
    {'DATE': '09.06.2025', 'DC CH NO.': 'F/03/25-26', 'Coil No': '41E601725', 'Material Sent From': 'Kapsons', 'MAKE': 'JSW', 'GRADE': '35C300', 'Coating': 'C5L', 'THK': '0.35', 'SIZE': '280', 'Net wt': '1369'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE1', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.35', 'SIZE': '283', 'Net wt': '2528'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE2', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.35', 'SIZE': '283', 'Net wt': '2228'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE3', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.35', 'SIZE': '287', 'Net wt': '2469'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE4', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.35', 'SIZE': '283', 'Net wt': '2508'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE5', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.35', 'SIZE': '283', 'Net wt': '2192'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE6', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.27', 'SIZE': '283', 'Net wt': '1323'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE7', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.35', 'SIZE': '283', 'Net wt': '2448'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE8', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.27', 'SIZE': '283', 'Net wt': '1298'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE9', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.27', 'SIZE': '286', 'Net wt': '2934'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE10', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.27', 'SIZE': '286', 'Net wt': '2794'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE11', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.35', 'SIZE': '283', 'Net wt': '2108'},
    {'DATE': '13/06/2025', 'DC CH NO.': 'F/04/25-26', 'Coil No': 'SSE12', 'Material Sent From': 'Vijay Poorena', 'MAKE': '', 'GRADE': '', 'Coating': '', 'THK': '0.35', 'SIZE': '283', 'Net wt': '2041'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/05/25-26', 'Coil No': 'I3E63914A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2450'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/05/25-26', 'Coil No': 'I3E63978A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2200'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/05/25-26', 'Coil No': 'I3E64642A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1156', 'Net wt': '2150'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/06/25-26', 'Coil No': 'I3E63960A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2690'},
    {'DATE': '28-07-2025', 'DC CH NO.': 'F/06/25-26', 'Coil No': 'I3E64760A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2730'},
    {'DATE': '28-07-2025', 'DC CH NO.': 'F/06/25-26', 'Coil No': 'I3E66420A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1156', 'Net wt': '1570'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/07/25-26', 'Coil No': 'I3E63982A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2200'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/07/25-26', 'Coil No': 'I3E64650A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1156', 'Net wt': '2380'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/07/25-26', 'Coil No': 'I3E64197A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1156', 'Net wt': '2610'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/07/25-26', 'Coil No': 'I3E63928A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2220'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/08/25-26', 'Coil No': 'I3E64638C', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1156', 'Net wt': '2000'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/08/25-26', 'Coil No': 'I3E63956A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2050'},
    {'DATE': '28-07-2025', 'DC CH NO.': 'F/08/25-26', 'Coil No': 'I3E66423A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1156', 'Net wt': '1550'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/09/25-26', 'Coil No': 'I3E64780A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2830'},
    {'DATE': '28-07-2025', 'DC CH NO.': 'F/09/25-26', 'Coil No': 'I3E64781A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2830'},
    {'DATE': '28-07-2025', 'DC CH NO.': 'F/09/25-26', 'Coil No': 'I3E64778A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2810'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/10/25-26', 'Coil No': 'I3E63929A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2510'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/10/25-26', 'Coil No': 'I3E63918A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2900'},
    {'DATE': '28-07-2025', 'DC CH NO.': 'F/10/25-26', 'Coil No': 'I3E64775A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2890'},
    {'DATE': '28-07-2025', 'DC CH NO.': 'F/10/25-26', 'Coil No': 'I3E64894A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1162', 'Net wt': '2080'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/11/25-26', 'Coil No': 'I3E63920A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2950'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/11/25-26', 'Coil No': 'I3E63981A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2970'},
    {'DATE': '26-07-2025', 'DC CH NO.': 'F/11/25-26', 'Coil No': 'I3E64779A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2780'},
    {'DATE': '28-07-2025', 'DC CH NO.': 'F/11/25-26', 'Coil No': 'I3E66421A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1156', 'Net wt': '1560'},
    {'DATE': '31-07-2025', 'DC CH NO.': 'F/14/25-26', 'Coil No': 'I3F02002D', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1156', 'Net wt': '5400'},
    {'DATE': '31-07-2025', 'DC CH NO.': 'F/14/25-26', 'Coil No': 'I3F06654BA', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '1680'},
    {'DATE': '30-07-2025', 'DC CH NO.': 'F/13/25-26', 'Coil No': 'I3E64638BA', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1156', 'Net wt': '2060'},
    {'DATE': '30-07-2025', 'DC CH NO.': 'F/13/25-26', 'Coil No': 'I3F06671BA', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '1680'},
    {'DATE': '30-07-2025', 'DC CH NO.': 'F/13/25-26', 'Coil No': 'I3F06708AA', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '1670'},
    {'DATE': '05-08-2025', 'DC CH NO.': 'F/15/25-26', 'Coil No': 'I3E64782A', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2970'},
    {'DATE': '05-08-2025', 'DC CH NO.': 'F/15/25-26', 'Coil No': 'I3F02178D', 'Material Sent From': 'POSCO', 'MAKE': 'POSCO', 'GRADE': '50C1000', 'Coating': '', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '6140'},
    {'DATE': '06.09.2025', 'DC CH NO.': 'F/17/25-26', 'Coil No': '56E500368', 'Material Sent From': 'KPS', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '1324'},
    {'DATE': '06.09.2025', 'DC CH NO.': 'F/17/25-26', 'Coil No': '56E500204', 'Material Sent From': 'KPS', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '1509'},
    {'DATE': '06.09.2025', 'DC CH NO.': 'F/17/25-26', 'Coil No': '56E500178', 'Material Sent From': 'KPS', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '973'},
    {'DATE': '06.09.2025', 'DC CH NO.': 'F/17/25-26', 'Coil No': '56E500367', 'Material Sent From': 'KPS', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '1232'},
    {'DATE': '06.09.2025', 'DC CH NO.': 'F/17/25-26', 'Coil No': '57E600253', 'Material Sent From': 'KPS', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '978'},
    {'DATE': '06.09.2025', 'DC CH NO.': 'F/17/25-26', 'Coil No': '56E600199', 'Material Sent From': 'KPS', 'MAKE': 'JSW', 'GRADE': '50C600', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '1176'},
    {'DATE': '06.09.2025', 'DC CH NO.': 'F/17/25-26', 'Coil No': '57E600518', 'Material Sent From': 'KPS', 'MAKE': 'JSW', 'GRADE': '50C530', 'Coating': 'C5L', 'THK': '0.5', 'SIZE': '1200', 'Net wt': '2450'},
]

def run_migration():
    """Runs the data migration script."""
    data_service = RMInwardService()
    
    print("Starting data migration...")
    for record in data_to_migrate:
        try:
            # Parse date, trying multiple formats
            date_str = record["DATE"]
            receipt_date = None
            for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    receipt_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    pass
            
            if not receipt_date:
                print(f"Could not parse date for record: {record}")
                continue

            # Handle coil supplier fallback and default values
            coil_supplier = record.get('MAKE') or record.get('Material Sent From') or 'N/A'
            
            # Handle numeric fields with default
            thk = float(record.get('THK') or 0)
            width = int(record.get('SIZE') or 0)
            coil_weight = float(record.get('Net wt') or 0)

            request_data = {
                "user_id": "tirthmehta@ambaltd.com",
                "rm_receipt_date": receipt_date,
                "rm_type": "N/A",
                "coil_number": str(record.get("Coil No") or 'N/A'),
                "grade": str(record.get("GRADE") or 'N/A'),
                "thk": thk,
                "width": width,
                "coating": str(record.get("Coating") or 'N/A'),
                "coil_weight": coil_weight,
                "po_number": str(record.get("DC CH NO.") or 'N/A'),
                "coil_supplier": coil_supplier,
                "coil_location": "Tenth",
            }

            request_obj = RMInwardIssueRequest(**request_data)
            
            print(f"Checking Coil No: {request_obj.coil_number}...")

            if data_service.is_coil_number_unique(request_obj.coil_number):
                print(f"  -> Migrating...")
                success = data_service.create_rm_inward_issue(request_obj)
                
                if success:
                    print(f"  -> Success!")
                else:
                    print(f"  -> FAILED.")
            else:
                print(f"  -> Skipped. Coil Number already exists.")
            
            # Be respectful to the API and avoid rate limiting
            time.sleep(1)

        except Exception as e:
            print(f"Error migrating record {record}: {e}")

    print("Data migration finished.")

if __name__ == "__main__":
    # To run this script, execute `python -m scripts.migration_script` from the root of the project.
    run_migration()