def get_report_url(report_type=None):
    # Define your report URLs here
    report_urls = {
        "FAF001 - Sales Report": 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF001.aspx',
        "FAF002 - Dosage Report": 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF002.aspx',
        "FAF003 - Report Of Other Imports And Exports": 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF003.aspx',
        "FAF004N - Internal Rotation Report (Imports)": 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF004.aspx',
        "FAF004X - Internal Rotation Report (Exports)": 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF004.aspx',
        "FAF005 - Detailed Report Of Imports": 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF005.aspx',
        "FAF006 - Supplier Return Report": 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF006.aspx',
        "FAF028 - Detailed Import - Export Transaction Report": 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF028.aspx',
        "FAF030 - FAF Inventory Report": 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF030.aspx',
    }
    if report_type:
        # Case-insensitive and whitespace-insensitive lookup
        normalized = report_type.strip().lower()
        for key, url in report_urls.items():
            if key.strip().lower() == normalized:
                return url
        return None
    return report_urls

link001 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF001.aspx'
link002 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF002.aspx'
link003 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF003.aspx'
link004 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF004.aspx'
link005 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF005.aspx'
link006 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF006.aspx'
link010 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF010.aspx'
link028 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF028.aspx'
link030 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF030.aspx'
link033 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHARFAF033.aspx'
link043 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHAR043.aspx'
link157 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHAR157.aspx'
link075 = 'https://bi.nhathuoclongchau.com.vn/MIS/PHAR/PHAR075.aspx'