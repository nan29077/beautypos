-- adpay MariaDB dump (from adpay.db SQLite)
SET FOREIGN_KEY_CHECKS=0;
SET NAMES utf8mb4;

DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `email` VARCHAR(255) NOT NULL,
  `password_hash` VARCHAR(255),
  `name` VARCHAR(100) NOT NULL,
  `role` VARCHAR(8) NOT NULL,
  `oauth_provider` VARCHAR(50),
  `oauth_sub` VARCHAR(255),
  `phone` VARCHAR(30),
  `is_active` TINYINT(1) NOT NULL,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME,
  `referral_code` VARCHAR(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `users` (`id`,`email`,`password_hash`,`name`,`role`,`oauth_provider`,`oauth_sub`,`phone`,`is_active`,`created_at`,`updated_at`,`referral_code`) VALUES
(1,'admin@test.com','$2b$12$trGslhqK3QVsWF6K3x2PLO18HtwkqhkZToE89a2giDzTclPQfwS1W','최고관리자','ADMIN',NULL,NULL,NULL,1,'2026-06-22 09:05:02.058450','2026-06-22 09:05:02.058450',NULL),
(2,'sales@test.com','$2b$12$trGslhqK3QVsWF6K3x2PLO18HtwkqhkZToE89a2giDzTclPQfwS1W','김영업','SALES',NULL,NULL,NULL,1,'2026-06-22 09:05:02.058450','2026-06-22 09:05:02.058450',NULL),
(3,'owner@test.com','$2b$12$trGslhqK3QVsWF6K3x2PLO18HtwkqhkZToE89a2giDzTclPQfwS1W','박원장','OWNER',NULL,NULL,NULL,1,'2026-06-22 09:05:02.058450','2026-06-22 09:05:02.058450',NULL),
(4,'designer@test.com','$2b$12$trGslhqK3QVsWF6K3x2PLO18HtwkqhkZToE89a2giDzTclPQfwS1W','홍길동','DESIGNER',NULL,NULL,NULL,1,'2026-06-22 09:05:02.058450','2026-06-22 09:05:02.058450',NULL),
(5,'designer2@test.com','$2b$12$trGslhqK3QVsWF6K3x2PLO18HtwkqhkZToE89a2giDzTclPQfwS1W','이디자','DESIGNER',NULL,NULL,NULL,1,'2026-06-22 09:05:02.058450','2026-06-22 09:05:02.058450',NULL);

DROP TABLE IF EXISTS `pg_providers`;
CREATE TABLE `pg_providers` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `code` VARCHAR(50) NOT NULL,
  `name` VARCHAR(100) NOT NULL,
  `is_active` TINYINT(1),
  `created_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `pg_providers` (`id`,`code`,`name`,`is_active`,`created_at`) VALUES
(1,'seedpayments','씨드페이먼츠',1,'2026-06-22 09:05:02.261880'),
(2,'kiwoompay','키움페이',1,'2026-06-22 09:05:02.261880'),
(3,'toss','토스',1,'2026-06-22 09:05:02.261880');

DROP TABLE IF EXISTS `affiliate_malls`;
CREATE TABLE `affiliate_malls` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `name` VARCHAR(200) NOT NULL,
  `logo_url` VARCHAR(500),
  `website_url` VARCHAR(500),
  `description` LONGTEXT,
  `category` VARCHAR(100),
  `commission_rate` VARCHAR(50),
  `is_active` TINYINT(1) NOT NULL,
  `sort_order` INT,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `system_configs`;
CREATE TABLE `system_configs` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `config_key` VARCHAR(100) NOT NULL,
  `config_value` VARCHAR(500),
  `is_enabled` TINYINT(1),
  `description` LONGTEXT,
  `updated_at` DATETIME,
  `created_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `merchants`;
CREATE TABLE `merchants` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `name` VARCHAR(200) NOT NULL,
  `owner_user_id` INT NOT NULL,
  `business_no` VARCHAR(50),
  `address` VARCHAR(500),
  `phone` VARCHAR(30),
  `category` VARCHAR(50),
  `category_custom` VARCHAR(100),
  `place_url` VARCHAR(500),
  `is_active` TINYINT(1) NOT NULL,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `merchants` (`id`,`name`,`owner_user_id`,`business_no`,`address`,`phone`,`category`,`category_custom`,`place_url`,`is_active`,`created_at`) VALUES
(1,'뷰티헤어살롱 강남점',3,'123-45-67890','서울 강남구 테헤란로 123','02-1234-5678','hair_salon',NULL,NULL,1,'2026-06-22 09:05:02.061449');

DROP TABLE IF EXISTS `payout_requests`;
CREATE TABLE `payout_requests` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `requester_user_id` INT NOT NULL,
  `role` VARCHAR(20) NOT NULL,
  `amount` NUMERIC(14, 2) NOT NULL,
  `bank_info` LONGTEXT,
  `memo` LONGTEXT,
  `status` VARCHAR(8),
  `created_at` DATETIME,
  `reviewed_at` DATETIME,
  `reviewed_by` INT,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `staff`;
CREATE TABLE `staff` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `user_id` INT,
  `name` VARCHAR(100) NOT NULL,
  `staff_code` VARCHAR(50) NOT NULL,
  `share_rate` NUMERIC(5, 4) NOT NULL,
  `is_active` TINYINT(1) NOT NULL,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `staff` (`id`,`merchant_id`,`user_id`,`name`,`staff_code`,`share_rate`,`is_active`,`created_at`) VALUES
(1,1,4,'홍길동','1',0.5,1,'2026-06-22 09:05:02.062451'),
(2,1,5,'이디자','2',0.5,1,'2026-06-22 09:05:02.062451');

DROP TABLE IF EXISTS `terminal_devices`;
CREATE TABLE `terminal_devices` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `terminal_serial` VARCHAR(100) NOT NULL,
  `api_key_hash` VARCHAR(255) NOT NULL,
  `memo` LONGTEXT,
  `is_active` TINYINT(1) NOT NULL,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `terminal_devices` (`id`,`merchant_id`,`terminal_serial`,`api_key_hash`,`memo`,`is_active`,`created_at`) VALUES
(1,1,'TERM001','$2b$12$iSfYdmXOu8GEP.NTNJ41ROn5WMGhqNFYJRUhDbQuEs4kaRKQ8U/.e','메인 카운터 단말기',1,'2026-06-22 09:05:02.259587');

DROP TABLE IF EXISTS `merchant_pg_configs`;
CREATE TABLE `merchant_pg_configs` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `provider_id` INT NOT NULL,
  `mid` VARCHAR(200) NOT NULL,
  `secret_encrypted` LONGTEXT NOT NULL,
  `status` VARCHAR(9),
  `last_tested_at` DATETIME,
  `created_at` DATETIME,
  `updated_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `merchant_pg_configs` (`id`,`merchant_id`,`provider_id`,`mid`,`secret_encrypted`,`status`,`last_tested_at`,`created_at`,`updated_at`) VALUES
(1,1,1,'MID-BEAUTY-001','gAAAAABqOPq-oEeWIPVMF1dF-W6OvL_QEPeBa6sSyuEFLo82tYbJKjkBkPHPJ1DDlnKVb3CvNd_6S4OovHI-xxeycgIwuOrxzVvnu-G5VX63Oo2neiRnFMs=','CONNECTED',NULL,'2026-06-22 09:05:02.267514','2026-06-22 09:05:02.267514');

DROP TABLE IF EXISTS `merchant_sales_assignments`;
CREATE TABLE `merchant_sales_assignments` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `sales_manager_user_id` INT NOT NULL,
  `commission_rate` NUMERIC(5, 4),
  `memo` LONGTEXT,
  `is_active` TINYINT(1) NOT NULL,
  `created_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `merchant_sales_assignments` (`id`,`merchant_id`,`sales_manager_user_id`,`commission_rate`,`memo`,`is_active`,`created_at`) VALUES
(1,1,2,0.01,NULL,1,'2026-06-22 09:05:02.269543');

DROP TABLE IF EXISTS `settlements`;
CREATE TABLE `settlements` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `period_start` DATETIME NOT NULL,
  `period_end` DATETIME NOT NULL,
  `gross_amount` NUMERIC(14, 2),
  `pg_fee_amount` NUMERIC(14, 2),
  `net_amount` NUMERIC(14, 2),
  `commission_amount` NUMERIC(14, 2),
  `created_at` DATETIME,
  `merchant_fee_amount` NUMERIC(14,2) DEFAULT '0',
  `company_profit_amount` NUMERIC(14,2) DEFAULT '0',
  `sales_manager_user_id` INT DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `ad_place_profiles`;
CREATE TABLE `ad_place_profiles` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `place_url` VARCHAR(500),
  `place_id` VARCHAR(200),
  `nickname` VARCHAR(200),
  `created_at` DATETIME,
  `analysis_keyword` VARCHAR(200) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `ad_place_profiles` (`id`,`merchant_id`,`place_url`,`place_id`,`nickname`,`created_at`,`analysis_keyword`) VALUES
(1,1,'https://map.naver.com/v5/entry/place/12345','12345','뷰티헤어살롱 강남','2026-06-22 09:05:02.277012',NULL);

DROP TABLE IF EXISTS `ad_competitors`;
CREATE TABLE `ad_competitors` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `competitor_place_url` VARCHAR(500) NOT NULL,
  `memo` LONGTEXT,
  `created_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `ad_competitors` (`id`,`merchant_id`,`competitor_place_url`,`memo`,`created_at`) VALUES
(1,1,'https://map.naver.com/v5/entry/place/67890','길 건너편 경쟁 미용실','2026-06-22 09:05:02.272427');

DROP TABLE IF EXISTS `ad_metrics`;
CREATE TABLE `ad_metrics` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `place_url` VARCHAR(500) NOT NULL,
  `date` DATE NOT NULL,
  `blog_review_count` INT,
  `visitor_review_count` INT,
  `place_rank` INT,
  `source` VARCHAR(50),
  `created_by` INT,
  `created_at` DATETIME,
  `search_keyword` VARCHAR(200) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `ad_metrics` (`id`,`merchant_id`,`place_url`,`date`,`blog_review_count`,`visitor_review_count`,`place_rank`,`source`,`created_by`,`created_at`,`search_keyword`) VALUES
(1,1,'https://map.naver.com/v5/entry/place/12345','2026-06-22',49,137,3,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(2,1,'https://map.naver.com/v5/entry/place/67890','2026-06-22',36,106,9,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(3,1,'https://map.naver.com/v5/entry/place/12345','2026-06-21',50,123,10,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(4,1,'https://map.naver.com/v5/entry/place/67890','2026-06-21',43,108,8,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(5,1,'https://map.naver.com/v5/entry/place/12345','2026-06-20',54,136,2,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(6,1,'https://map.naver.com/v5/entry/place/67890','2026-06-20',49,110,6,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(7,1,'https://map.naver.com/v5/entry/place/12345','2026-06-19',55,133,2,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(8,1,'https://map.naver.com/v5/entry/place/67890','2026-06-19',37,93,4,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(9,1,'https://map.naver.com/v5/entry/place/12345','2026-06-18',45,135,8,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(10,1,'https://map.naver.com/v5/entry/place/67890','2026-06-18',37,94,8,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(11,1,'https://map.naver.com/v5/entry/place/12345','2026-06-17',52,124,2,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(12,1,'https://map.naver.com/v5/entry/place/67890','2026-06-17',50,109,1,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(13,1,'https://map.naver.com/v5/entry/place/12345','2026-06-16',47,128,4,'manual',1,'2026-06-22 09:05:02.273958',NULL),
(14,1,'https://map.naver.com/v5/entry/place/67890','2026-06-16',39,97,4,'manual',1,'2026-06-22 09:05:02.273958',NULL);

DROP TABLE IF EXISTS `ad_orders`;
CREATE TABLE `ad_orders` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `type` VARCHAR(13) NOT NULL,
  `status` VARCHAR(9),
  `created_by` INT NOT NULL,
  `assigned_admin_id` INT,
  `admin_memo` LONGTEXT,
  `created_at` DATETIME,
  `updated_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `ad_orders` (`id`,`merchant_id`,`type`,`status`,`created_by`,`assigned_admin_id`,`admin_memo`,`created_at`,`updated_at`) VALUES
(1,1,'BLOG','REVIEWING',3,NULL,NULL,'2026-06-22 09:05:02.274971','2026-06-22 09:05:02.274971'),
(2,1,'PLACE_TRAFFIC','REQUESTED',3,NULL,NULL,'2026-06-22 09:05:02.279043','2026-06-22 09:05:02.279043');

DROP TABLE IF EXISTS `receipt_review_configs`;
CREATE TABLE `receipt_review_configs` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `token` VARCHAR(64) NOT NULL,
  `place_url` VARCHAR(500),
  `welcome_message` LONGTEXT,
  `is_active` TINYINT(1) NOT NULL,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `transactions`;
CREATE TABLE `transactions` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `terminal_id` INT,
  `staff_id` INT,
  `owner_user_id` INT,
  `amount` NUMERIC(12, 2) NOT NULL,
  `installment_months` INT,
  `card_brand` VARCHAR(50),
  `approval_code` VARCHAR(100),
  `staff_code_input` VARCHAR(50),
  `approved_at` DATETIME,
  `raw_payload_json` LONGTEXT,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `transactions` (`id`,`merchant_id`,`terminal_id`,`staff_id`,`owner_user_id`,`amount`,`installment_months`,`card_brand`,`approval_code`,`staff_code_input`,`approved_at`,`raw_payload_json`,`created_at`) VALUES
(1,1,1,1,3,35000,6,'현대카드','APR-182146','1','2026-06-01 22:05:02.270058',NULL,'2026-06-02 01:05:02.270058'),
(2,1,1,1,3,75000,6,'삼성카드','APR-237115','1','2026-05-26 01:05:02.270058',NULL,'2026-05-25 23:05:02.270058'),
(3,1,1,1,3,35000,6,'삼성카드','APR-450318','1','2026-05-25 01:05:02.270058',NULL,'2026-05-25 05:05:02.270058'),
(4,1,1,1,3,35000,0,'MASTER','APR-538668','1','2026-06-01 05:05:02.270058',NULL,'2026-06-01 09:05:02.270058'),
(5,1,1,2,3,100000,0,'삼성카드','APR-554339','2','2026-06-11 21:05:02.270058',NULL,'2026-06-12 06:05:02.270058'),
(6,1,1,2,3,35000,3,'삼성카드','APR-609224','2','2026-06-16 07:05:02.270058',NULL,'2026-06-16 03:05:02.270058'),
(7,1,1,2,3,50000,0,'현대카드','APR-695076','2','2026-06-11 09:05:02.270058',NULL,'2026-06-10 23:05:02.270058'),
(8,1,1,NULL,3,15000,0,'VISA','APR-885444',NULL,'2026-06-22 03:05:02.270058',NULL,'2026-06-22 07:05:02.270058'),
(9,1,1,NULL,3,15000,3,'MASTER','APR-830545',NULL,'2026-06-15 05:05:02.270058',NULL,'2026-06-14 23:05:02.270058'),
(10,1,1,NULL,3,25000,6,'MASTER','APR-688898',NULL,'2026-06-16 23:05:02.270058',NULL,'2026-06-16 23:05:02.270058');

DROP TABLE IF EXISTS `ad_order_blog_details`;
CREATE TABLE `ad_order_blog_details` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `order_id` INT NOT NULL,
  `campaign_name` VARCHAR(300) NOT NULL,
  `address` VARCHAR(500),
  `contact` VARCHAR(100),
  `links_json` LONGTEXT,
  `main_keywords_json` LONGTEXT,
  `hashtags_json` LONGTEXT,
  `description` LONGTEXT,
  `extra_image_link` LONGTEXT,
  `created_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `ad_order_blog_details` (`id`,`order_id`,`campaign_name`,`address`,`contact`,`links_json`,`main_keywords_json`,`hashtags_json`,`description`,`extra_image_link`,`created_at`) VALUES
(1,1,'뷰티헤어살롱 강남점 블로그 리뷰','서울 강남구 테헤란로 123','02-1234-5678','["https://map.naver.com/v5/entry/place/12345", "https://instagram.com/beauty_hair_gn"]','["\\uac15\\ub0a8\\ubbf8\\uc6a9\\uc2e4", "\\uac15\\ub0a8\\ud5e4\\uc5b4\\uc0b4\\ub871", "\\uac15\\ub0a8\\ud38c", "\\uac15\\ub0a8\\uc5fc\\uc0c9", "\\ud14c\\ud5e4\\ub780\\ub85c\\ubbf8\\uc6a9\\uc2e4"]','["#\\uac15\\ub0a8\\ubbf8\\uc6a9\\uc2e4", "#\\uac15\\ub0a8\\ud5e4\\uc5b4\\uc0b4\\ub871", "#\\uac15\\ub0a8\\ud38c\\ucd94\\ucc9c"]','강남역 5분 거리 프리미엄 헤어살롱. 트렌디한 스타일링과 친절한 서비스.',NULL,'2026-06-22 09:05:02.280055');

DROP TABLE IF EXISTS `ad_order_blog_images`;
CREATE TABLE `ad_order_blog_images` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `order_id` INT NOT NULL,
  `file_path` VARCHAR(500) NOT NULL,
  `created_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `ad_order_place_traffic_details`;
CREATE TABLE `ad_order_place_traffic_details` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `order_id` INT NOT NULL,
  `place_name_or_id` VARCHAR(300) NOT NULL,
  `search_keywords_json` LONGTEXT,
  `created_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `ad_order_place_traffic_details` (`id`,`order_id`,`place_name_or_id`,`search_keywords_json`,`created_at`) VALUES
(1,2,'뷰티헤어살롱 강남점','["\\uac15\\ub0a8\\ubbf8\\uc6a9\\uc2e4", "\\uac15\\ub0a8\\ud5e4\\uc5b4", "\\ud14c\\ud5e4\\ub780\\ub85c\\ubbf8\\uc6a9\\uc2e4"]','2026-06-22 09:05:02.281248');

DROP TABLE IF EXISTS `receipt_reviews`;
CREATE TABLE `receipt_reviews` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `config_id` INT NOT NULL,
  `customer_phone` VARCHAR(30),
  `customer_name` VARCHAR(100),
  `receipt_image_url` VARCHAR(500),
  `status` VARCHAR(20) NOT NULL,
  `review_completed` TINYINT(1),
  `memo` LONGTEXT,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `crm_customers`;
CREATE TABLE `crm_customers` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `name` VARCHAR(100) NOT NULL,
  `phone` VARCHAR(30),
  `gender` VARCHAR(10),
  `birthday` DATE,
  `anniversary` DATE,
  `memo` LONGTEXT,
  `allergy_memo` LONGTEXT,
  `hair_memo` LONGTEXT,
  `photo_url` VARCHAR(500),
  `tags` VARCHAR(300),
  `assigned_staff_id` INT,
  `preferred_staff_id` INT,
  `preferred_service` VARCHAR(200),
  `points` INT NOT NULL,
  `last_message_at` DATETIME,
  `is_active` TINYINT(1) NOT NULL,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `crm_customers` (`id`,`merchant_id`,`name`,`phone`,`gender`,`birthday`,`anniversary`,`memo`,`allergy_memo`,`hair_memo`,`photo_url`,`tags`,`assigned_staff_id`,`preferred_staff_id`,`preferred_service`,`points`,`last_message_at`,`is_active`,`created_at`,`updated_at`) VALUES
(1,1,'김지영','010-2345-6789','female','1990-07-15',NULL,'컬러 밝게 선호','암모니아 염모제 알레르기 (패치테스트 필수)','모발 가늘고 손상모, 클리닉 병행 권장',NULL,'단골,염색',1,1,'뿌리염색',24000,NULL,1,'2026-07-02 01:48:29.652420','2026-07-27 01:48:29.665420'),
(2,1,'박서연','010-9871-2345','female','1982-07-22',NULL,'예약 시 창가자리 선호',NULL,'굵은 직모, 펌 잘 풀림',NULL,'단골,VIP',2,2,'디지털펌',18000,NULL,1,'2026-06-29 01:48:29.652420','2026-07-27 01:48:29.665420'),
(3,1,'이민재','010-4423-1100','male','1995-03-03',NULL,'',NULL,NULL,NULL,'일반',1,1,'남성컷',12000,NULL,1,'2026-03-23 01:48:29.652420','2026-07-27 01:48:29.665420'),
(4,1,'정수빈','010-5510-2233','female','1990-07-09',NULL,'주말 오후 선호',NULL,'반곱슬',NULL,'일반',2,2,'드라이/스타일링',10000,NULL,1,'2026-06-07 01:48:29.652420','2026-07-27 01:48:29.665420'),
(5,1,'최예린','010-7702-8890','female','1981-07-05',NULL,'',NULL,NULL,NULL,'신규',1,1,'일반염색',4000,NULL,1,'2026-03-29 01:48:29.652420','2026-07-27 01:48:29.665420'),
(6,1,'한도윤','010-3398-4521','male','1989-11-28',NULL,'재방문 유도 필요',NULL,NULL,NULL,'휴면',2,2,'컷',6000,NULL,1,'2026-03-15 01:48:29.652420','2026-07-27 01:48:29.665420'),
(7,1,'윤하늘','010-6611-7788','female','1981-05-17',NULL,'','두피 예민','염색 이력 많음',NULL,'휴면',1,1,'두피클리닉',4000,NULL,1,'2026-01-03 01:48:29.652420','2026-07-27 01:48:29.665420'),
(8,1,'장은우','010-2244-3366','female','1984-07-27',NULL,'친구 추천 방문',NULL,NULL,NULL,'신규,친구추천',2,2,'컷',2000,NULL,1,'2026-03-03 01:48:29.652420','2026-07-27 01:48:29.665420');

DROP TABLE IF EXISTS `crm_services`;
CREATE TABLE `crm_services` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `name` VARCHAR(100) NOT NULL,
  `category` VARCHAR(50),
  `price` NUMERIC(12, 0) NOT NULL,
  `duration_min` INT NOT NULL,
  `is_active` TINYINT(1) NOT NULL,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `crm_services` (`id`,`merchant_id`,`name`,`category`,`price`,`duration_min`,`is_active`,`created_at`) VALUES
(1,1,'컷','커트',25000,40,1,'2026-07-27 01:48:29.658422'),
(2,1,'남성컷','커트',20000,30,1,'2026-07-27 01:48:29.658422'),
(3,1,'일반염색','염색',70000,90,1,'2026-07-27 01:48:29.658422'),
(4,1,'뿌리염색','염색',50000,70,1,'2026-07-27 01:48:29.658422'),
(5,1,'디지털펌','펌',120000,150,1,'2026-07-27 01:48:29.658422'),
(6,1,'열펌','펌',100000,130,1,'2026-07-27 01:48:29.658422'),
(7,1,'두피클리닉','클리닉',50000,60,1,'2026-07-27 01:48:29.658422'),
(8,1,'드라이/스타일링','스타일링',30000,40,1,'2026-07-27 01:48:29.658422');

DROP TABLE IF EXISTS `crm_message_templates`;
CREATE TABLE `crm_message_templates` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `name` VARCHAR(100) NOT NULL,
  `channel` VARCHAR(8) NOT NULL,
  `category` VARCHAR(50),
  `body` LONGTEXT NOT NULL,
  `is_active` TINYINT(1) NOT NULL,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `crm_message_templates` (`id`,`merchant_id`,`name`,`channel`,`category`,`body`,`is_active`,`created_at`) VALUES
(1,1,'예약 리마인더','SMS','reminder','[{매장명}] {고객명}님, 예약일이 다가왔습니다. 방문 부탁드립니다 :)',1,'2026-07-27 01:48:29.666420'),
(2,1,'생일 축하','ALIMTALK','birthday','[{매장명}] {고객명}님, 생일 축하드립니다! 생일 기념 10% 할인 쿠폰을 드려요.',1,'2026-07-27 01:48:29.666420'),
(3,1,'재방문 유도','SMS','dormant','[{매장명}] {고객명}님, 오랜만이에요! 보유 포인트 {포인트}P로 더 알뜰하게 관리받으세요.',1,'2026-07-27 01:48:29.666420'),
(4,1,'방문 감사','SMS','thanks','[{매장명}] {고객명}님, 오늘 방문 감사합니다. 다음에도 예쁘게 관리해 드릴게요!',1,'2026-07-27 01:48:29.666420');

DROP TABLE IF EXISTS `crm_service_prices`;
CREATE TABLE `crm_service_prices` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `service_id` INT NOT NULL,
  `staff_id` INT NOT NULL,
  `price` NUMERIC(12, 0) NOT NULL,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `crm_visits`;
CREATE TABLE `crm_visits` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `customer_id` INT NOT NULL,
  `staff_id` INT,
  `service_name` VARCHAR(200),
  `amount` NUMERIC(12, 0) NOT NULL,
  `memo` LONGTEXT,
  `visit_date` DATETIME NOT NULL,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `crm_visits` (`id`,`merchant_id`,`customer_id`,`staff_id`,`service_name`,`amount`,`memo`,`visit_date`,`created_at`) VALUES
(1,1,1,1,'뿌리염색',50000,NULL,'2026-07-16 13:00:29.652420','2026-07-16 13:00:29.652420'),
(2,1,1,1,'디지털펌',120000,NULL,'2026-06-09 17:00:29.652420','2026-06-09 17:00:29.652420'),
(3,1,1,1,'일반염색',70000,NULL,'2026-05-27 16:00:29.652420','2026-05-27 16:00:29.652420'),
(4,1,1,1,'컷',25000,NULL,'2026-03-18 19:00:29.652420','2026-03-18 19:00:29.652420'),
(5,1,1,1,'두피클리닉',50000,NULL,'2026-02-06 16:00:29.652420','2026-02-06 16:00:29.652420'),
(6,1,1,1,'남성컷',20000,NULL,'2026-02-21 18:30:29.652420','2026-02-21 18:30:29.652420'),
(7,1,1,1,'디지털펌',120000,NULL,'2025-11-18 14:30:29.652420','2025-11-18 14:30:29.652420'),
(8,1,1,1,'남성컷',20000,NULL,'2026-01-08 13:30:29.652420','2026-01-08 13:30:29.652420'),
(9,1,1,1,'남성컷',20000,NULL,'2025-11-02 14:00:29.652420','2025-11-02 14:00:29.652420'),
(10,1,1,1,'디지털펌',120000,NULL,'2025-08-08 11:00:29.652420','2025-08-08 11:00:29.652420'),
(11,1,1,1,'뿌리염색',50000,NULL,'2025-09-09 14:00:29.652420','2025-09-09 14:00:29.652420'),
(12,1,1,1,'일반염색',70000,NULL,'2025-09-11 15:00:29.652420','2025-09-11 15:00:29.652420'),
(13,1,2,2,'열펌',100000,NULL,'2026-07-21 11:30:29.652420','2026-07-21 11:30:29.652420'),
(14,1,2,2,'남성컷',20000,NULL,'2026-06-14 10:00:29.652420','2026-06-14 10:00:29.652420'),
(15,1,2,2,'드라이/스타일링',30000,NULL,'2026-06-05 17:30:29.652420','2026-06-05 17:30:29.652420'),
(16,1,2,2,'컷',25000,NULL,'2026-05-22 18:30:29.652420','2026-05-22 18:30:29.652420'),
(17,1,2,2,'두피클리닉',50000,NULL,'2026-04-24 15:00:29.652420','2026-04-24 15:00:29.652420'),
(18,1,2,2,'남성컷',20000,NULL,'2026-01-27 17:30:29.652420','2026-01-27 17:30:29.652420'),
(19,1,2,2,'뿌리염색',50000,NULL,'2026-01-04 14:30:29.652420','2026-01-04 14:30:29.652420'),
(20,1,2,2,'일반염색',70000,NULL,'2025-12-16 18:30:29.652420','2025-12-16 18:30:29.652420'),
(21,1,2,2,'드라이/스타일링',30000,NULL,'2026-02-11 10:30:29.652420','2026-02-11 10:30:29.652420'),
(22,1,3,1,'두피클리닉',50000,NULL,'2026-07-10 15:30:29.652420','2026-07-10 15:30:29.652420'),
(23,1,3,1,'일반염색',70000,NULL,'2026-06-20 17:00:29.652420','2026-06-20 17:00:29.652420'),
(24,1,3,1,'드라이/스타일링',30000,NULL,'2026-04-23 10:30:29.652420','2026-04-23 10:30:29.652420'),
(25,1,3,1,'열펌',100000,NULL,'2026-04-26 16:30:29.652420','2026-04-26 16:30:29.652420'),
(26,1,3,1,'뿌리염색',50000,NULL,'2026-02-04 17:00:29.652420','2026-02-04 17:00:29.652420'),
(27,1,3,1,'디지털펌',120000,NULL,'2026-02-25 18:00:29.652420','2026-02-25 18:00:29.652420'),
(28,1,4,2,'두피클리닉',50000,NULL,'2026-07-22 17:00:29.652420','2026-07-22 17:00:29.652420'),
(29,1,4,2,'뿌리염색',50000,NULL,'2026-06-18 18:00:29.652420','2026-06-18 18:00:29.652420'),
(30,1,4,2,'디지털펌',120000,NULL,'2026-05-25 18:00:29.652420','2026-05-25 18:00:29.652420'),
(31,1,4,2,'남성컷',20000,NULL,'2026-05-17 16:30:29.652420','2026-05-17 16:30:29.652420'),
(32,1,4,2,'열펌',100000,NULL,'2026-02-28 17:00:29.652420','2026-02-28 17:00:29.652420'),
(33,1,5,1,'남성컷',20000,NULL,'2026-07-26 10:00:29.652420','2026-07-26 10:00:29.652420'),
(34,1,5,1,'두피클리닉',50000,NULL,'2026-06-23 17:30:29.652420','2026-06-23 17:30:29.652420'),
(35,1,6,2,'디지털펌',120000,NULL,'2026-05-17 16:30:29.652420','2026-05-17 16:30:29.652420'),
(36,1,6,2,'남성컷',20000,NULL,'2026-04-09 13:30:29.652420','2026-04-09 13:30:29.652420'),
(37,1,6,2,'컷',25000,NULL,'2026-04-07 17:30:29.652420','2026-04-07 17:30:29.652420'),
(38,1,7,1,'두피클리닉',50000,NULL,'2026-04-07 19:00:29.652420','2026-04-07 19:00:29.652420'),
(39,1,7,1,'뿌리염색',50000,NULL,'2026-03-02 16:00:29.652420','2026-03-02 16:00:29.652420'),
(40,1,8,2,'드라이/스타일링',30000,NULL,'2026-07-22 19:00:29.652420','2026-07-22 19:00:29.652420');

DROP TABLE IF EXISTS `crm_reservations`;
CREATE TABLE `crm_reservations` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `customer_id` INT,
  `customer_name` VARCHAR(100),
  `phone` VARCHAR(30),
  `staff_id` INT,
  `service_name` VARCHAR(200),
  `reserved_at` DATETIME NOT NULL,
  `end_at` DATETIME,
  `duration_min` INT,
  `status` VARCHAR(9) NOT NULL,
  `memo` LONGTEXT,
  `reminder_sent_at` DATETIME,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `crm_reservations` (`id`,`merchant_id`,`customer_id`,`customer_name`,`phone`,`staff_id`,`service_name`,`reserved_at`,`end_at`,`duration_min`,`status`,`memo`,`reminder_sent_at`,`created_at`) VALUES
(1,1,1,'김지영','010-2345-6789',1,'뿌리염색','2026-07-27 11:00:00.000000','2026-07-27 12:10:00.000000',70,'CONFIRMED',NULL,NULL,'2026-07-27 01:48:29.669422'),
(2,1,2,'박서연','010-9871-2345',2,'디지털펌','2026-07-27 14:00:00.000000','2026-07-27 16:30:00.000000',150,'BOOKED',NULL,NULL,'2026-07-27 01:48:29.669422'),
(3,1,3,'이민재','010-4423-1100',1,'컷','2026-07-27 16:00:00.000000','2026-07-27 16:40:00.000000',40,'CONFIRMED',NULL,NULL,'2026-07-27 01:48:29.669422'),
(4,1,4,'정수빈','010-5510-2233',2,'두피클리닉','2026-07-28 13:00:00.000000','2026-07-28 14:00:00.000000',60,'BOOKED',NULL,NULL,'2026-07-27 01:48:29.669422'),
(5,1,5,'최예린','010-7702-8890',1,'일반염색','2026-07-29 15:00:00.000000','2026-07-29 16:30:00.000000',90,'BOOKED',NULL,NULL,'2026-07-27 01:48:29.669422'),
(6,1,8,'장은우','010-2244-3366',2,'컷','2026-07-30 10:00:00.000000','2026-07-30 10:40:00.000000',40,'BOOKED',NULL,NULL,'2026-07-27 01:48:29.669422');

DROP TABLE IF EXISTS `crm_point_logs`;
CREATE TABLE `crm_point_logs` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `customer_id` INT NOT NULL,
  `delta` INT NOT NULL,
  `reason` VARCHAR(200),
  `balance_after` INT NOT NULL,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `crm_point_logs` (`id`,`merchant_id`,`customer_id`,`delta`,`reason`,`balance_after`,`created_at`) VALUES
(1,1,1,24000,'누적 적립',24000,'2026-07-16 01:48:29.652420'),
(2,1,2,18000,'누적 적립',18000,'2026-07-21 01:48:29.652420'),
(3,1,3,12000,'누적 적립',12000,'2026-07-10 01:48:29.652420'),
(4,1,4,10000,'누적 적립',10000,'2026-07-22 01:48:29.652420'),
(5,1,5,4000,'누적 적립',4000,'2026-07-26 01:48:29.652420'),
(6,1,6,6000,'누적 적립',6000,'2026-05-17 01:48:29.652420'),
(7,1,7,4000,'누적 적립',4000,'2026-04-07 01:48:29.652420'),
(8,1,8,2000,'누적 적립',2000,'2026-07-22 01:48:29.652420');

DROP TABLE IF EXISTS `crm_message_logs`;
CREATE TABLE `crm_message_logs` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `customer_id` INT,
  `template_id` INT,
  `channel` VARCHAR(8) NOT NULL,
  `to_phone` VARCHAR(30),
  `content` LONGTEXT NOT NULL,
  `status` VARCHAR(6) NOT NULL,
  `campaign` VARCHAR(50),
  `sent_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `crm_coupons`;
CREATE TABLE `crm_coupons` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `customer_id` INT,
  `name` VARCHAR(120) NOT NULL,
  `discount_type` VARCHAR(20) NOT NULL,
  `value` INT NOT NULL,
  `status` VARCHAR(7) NOT NULL,
  `expires_at` DATE,
  `used_at` DATETIME,
  `memo` VARCHAR(200),
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `crm_coupons` (`id`,`merchant_id`,`customer_id`,`name`,`discount_type`,`value`,`status`,`expires_at`,`used_at`,`memo`,`created_at`) VALUES
(1,1,2,'VIP 15% 할인','percent',15,'ISSUED','2026-09-25',NULL,'VIP 감사 쿠폰','2026-07-27 01:48:29.664424'),
(2,1,6,'재방문 1만원 할인','amount',10000,'ISSUED','2026-08-26',NULL,'휴면 고객 컴백','2026-07-27 01:48:29.664424');

DROP TABLE IF EXISTS `sales_commission_policies`;
CREATE TABLE `sales_commission_policies` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `sales_manager_user_id` INT,
  `commission_rate` NUMERIC(5, 4),
  `created_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `place_metric_snapshots`;
CREATE TABLE `place_metric_snapshots` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT NOT NULL,
  `date` DATE NOT NULL,
  `place_id` VARCHAR(50) NOT NULL,
  `place_url` VARCHAR(500),
  `place_name` VARCHAR(300),
  `kind` VARCHAR(20),
  `blog_count` INT,
  `visitor_count` INT,
  `rank` INT,
  `keyword` VARCHAR(200),
  `collected_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `fee_policies`;
CREATE TABLE `fee_policies` (
  `id` INT AUTO_INCREMENT NOT NULL,
  `merchant_id` INT,
  `merchant_fee_rate` NUMERIC(5,4) DEFAULT '0.05',
  `pg_fee_rate` NUMERIC(5,4) DEFAULT '0.03',
  `vat_inclusive_rate` NUMERIC(5,4),
  `updated_at` DATETIME,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `fee_policies` (`id`,`merchant_id`,`merchant_fee_rate`,`pg_fee_rate`,`vat_inclusive_rate`,`updated_at`) VALUES
(1,1,0.05,0.033,0.0385,'2026-06-22 09:05:02.268022');

SET FOREIGN_KEY_CHECKS=1;