import logging
import os
import time
from typing import List

import pandas as pd
import requests


# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OrderProcessor:
    def __init__(self, db_config: dict, output_file: str = 'unique_order_ids.txt'):
        self.db_config = db_config
        self.output_file = output_file
        self.api_base_url = "http://127.0.0.1:8090/restful_server/india/unified/submit"

    def get_unique_order_ids_from_db(self) -> List[str]:
        """从数据库获取不重复的订单ID"""
        try:
            # 使用SQLAlchemy或直接连接数据库
            import sqlalchemy as db

            engine = db.create_engine(
                f"mysql+pymysql://{self.db_config['user']}:{self.db_config['password']}@"
                f"{self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}"
            )

            query = "SELECT DISTINCT id FROM ods_orders"
            df = pd.read_sql(query, engine)

            unique_ids = df['id'].tolist()
            logger.info(f"获取到 {len(unique_ids)} 个不重复的订单ID")
            return unique_ids

        except ImportError:
            # 如果没有SQLAlchemy，使用其他方式连接数据库
            logger.warning("SQLAlchemy未安装，使用其他方式连接数据库")
            return self._get_ids_alternative()

    def _get_ids_alternative(self) -> List[str]:
        """替代的数据库连接方式"""
        try:
            import pymysql

            connection = pymysql.connect(
                host=self.db_config['host'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database'],
                port=self.db_config.get('port', 3306)
            )

            with connection.cursor() as cursor:
                cursor.execute("SELECT DISTINCT id FROM ods_orders")
                results = cursor.fetchall()
                unique_ids = [str(row[0]) for row in results]
                logger.info(f"获取到 {len(unique_ids)} 个不重复的订单ID")
                return unique_ids

        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            return []

    def save_ids_to_file(self, order_ids: List[str]):
        """将订单ID保存到文件"""
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                for order_id in order_ids:
                    f.write(f"{order_id}\n")
            logger.info(f"订单ID已保存到文件: {self.output_file}")
        except Exception as e:
            logger.error(f"保存文件失败: {e}")

    def read_ids_from_file(self, batch_size: int = 100) -> List[List[str]]:
        """从文件读取订单ID并分批"""
        try:
            with open(self.output_file, 'r', encoding='utf-8') as f:
                all_ids = [line.strip() for line in f if line.strip()]

            # 分批处理
            batches = []
            for i in range(0, len(all_ids), batch_size):
                batch = all_ids[i:i + batch_size]
                batches.append(batch)

            logger.info(f"从文件读取到 {len(all_ids)} 个订单ID，分成 {len(batches)} 批")
            return batches

        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            return []

    def call_api_for_batch(self, batch: List[str], delay: float = 0.1) -> dict:
        """调用API处理一批订单ID"""
        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }

        for order_id in batch:
            try:
                url = f"{self.api_base_url}/{order_id}?expire= 12 * 60 * 60"
                response = requests.get(url, timeout=30)

                if response.status_code == 200:
                    if response.json().get("status") == 403:
                        results['failed'] += 1
                        logger.info(f"订单 {order_id} 重复提交")
                    else:
                        results['success'] += 1
                        logger.info(f"订单 {order_id} 处理成功")
                else:
                    results['failed'] += 1
                    logger.warning(f"订单 {order_id} 处理失败，状态码: {response.status_code}")
                    results['errors'].append(f"订单 {order_id}: 状态码 {response.status_code}")

                # 添加延迟，避免对服务器造成过大压力
                time.sleep(delay)

            except requests.exceptions.RequestException as e:
                results['failed'] += 1
                logger.error(f"订单 {order_id} 请求异常: {e}")
                results['errors'].append(f"订单 {order_id}: {str(e)}")
            except Exception as e:
                results['failed'] += 1
                logger.error(f"订单 {order_id} 处理异常: {e}")
                results['errors'].append(f"订单 {order_id}: {str(e)}")

        return results

    def process_all_batches(self, batch_size: int = 100, delay: float = 0.1):
        """处理所有批次的订单"""
        batches = self.read_ids_from_file(batch_size)

        total_results = {
            'total_batches': len(batches),
            'total_success': 0,
            'total_failed': 0,
            'all_errors': []
        }

        for i, batch in enumerate(batches, 1):
            logger.info(f"正在处理第 {i}/{len(batches)} 批，本批 {len(batch)} 个订单")

            batch_results = self.call_api_for_batch(batch, delay)

            total_results['total_success'] += batch_results['success']
            total_results['total_failed'] += batch_results['failed']
            total_results['all_errors'].extend(batch_results['errors'])

            logger.info(f"第 {i} 批处理完成: 成功 {batch_results['success']}, 失败 {batch_results['failed']}")

        # 输出总结
        logger.info("所有批次处理完成!")
        logger.info(f"总计: 成功 {total_results['total_success']}, 失败 {total_results['total_failed']}")

        if total_results['all_errors']:
            logger.warning(f"共有 {len(total_results['all_errors'])} 个错误")
            with open('error_log.txt', 'w', encoding='utf-8') as f:
                for error in total_results['all_errors']:
                    f.write(f"{error}\n")

# 使用示例
if __name__ == "__main__":
    # 数据库配置
    db_config = {
        'host': '172.22.32.17',
        'port': 9030,
        'user': 'jingboZhang',
        'password': '7$pL9!qR2*tW4#x',
        'database': 'India'
    }
    output_file = "/home/ubuntu/restful_server/unified_test/unique_order_ids.txt"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    processor = OrderProcessor(db_config=db_config, output_file=output_file)

    # 第一步：从数据库获取不重复订单ID并保存到文件
    # unique_ids = processor.get_unique_order_ids_from_db()
    # processor.save_ids_to_file(unique_ids)

    # 第二步：从文件读取并分批调用API
    processor.process_all_batches(batch_size=100, delay=0.1)
