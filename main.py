"""
JMS数据工具 - 统一入口
"""
import sys
import asyncio
from datetime import datetime, timedelta

from login import JMSLogin


def show_menu():
    """显示功能菜单"""
    print("\n" + "=" * 50)
    print("JMS 数据工具")
    print("=" * 50)
    print("1. 下载虚假签收报表")
    print("2. 实时数据采集（推送CRM）")
    print("3. Token管理服务")
    print("0. 退出")
    print("=" * 50)


def get_date_input() -> str:
    """获取日期输入，默认昨天"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    date_input = input(f"请输入日期 (默认 {yesterday}): ").strip()
    return date_input if date_input else yesterday


async def run_false_sign(date: str = None):
    """运行虚假签收报表下载"""
    from modules.false_sign import FalseSignModule
    
    # 1. 登录获取token
    login = JMSLogin()
    success = await login.login()
    
    if not success:
        print("[错误] 登录失败，无法获取有效token")
        return
    
    # 2. 下载报表
    module = FalseSignModule(authtoken=login.authtoken)
    output_path = module.run(date=date)
    
    if output_path:
        print(f"\n[完成] 报表已导出: {output_path}")
    else:
        print("\n[失败] 报表导出失败")


async def run_realtime_crawler():
    """运行实时数据采集"""
    from crawler import JMSDataCrawler
    
    # 1. 登录获取token
    login = JMSLogin()
    success = await login.login()
    
    if not success:
        print("[错误] 登录失败")
        return
    
    # 2. 启动数据采集循环
    print("\n[数据采集] 开始后台循环采集，间隔 30 秒")
    print("[数据采集] 按 Ctrl+C 退出")
    print("=" * 50)
    
    crawler = JMSDataCrawler(login.authtoken)
    query_count = 0
    
    while True:
        try:
            query_count += 1
            print(f"\n[第 {query_count} 次采集]")
            
            success = crawler.fetch_and_push()
            if not success:
                print("[服务停止] 推送失败")
                break
            
            print("等待 30 秒...")
            await asyncio.sleep(30)
        except KeyboardInterrupt:
            print("\n\n[退出] 程序已停止")
            break


async def run_token_manager():
    """运行Token管理服务"""
    from token_manager import run_server
    from token_manager.config import SERVER_HOST, SERVER_PORT, KEEP_ALIVE_INTERVAL
    
    print("\n" + "=" * 50)
    print("Token管理服务配置")
    print("=" * 50)
    
    # 获取配置选项
    host_input = input(f"服务地址 (默认 {SERVER_HOST}): ").strip()
    host = host_input if host_input else SERVER_HOST
    
    port_input = input(f"服务端口 (默认 {SERVER_PORT}): ").strip()
    try:
        port = int(port_input) if port_input else SERVER_PORT
    except ValueError:
        print(f"[警告] 无效端口，使用默认值 {SERVER_PORT}")
        port = SERVER_PORT
    
    keeper_input = input("启用Token保活服务? (Y/n): ").strip().lower()
    enable_keeper = keeper_input != 'n'
    
    keeper_interval = KEEP_ALIVE_INTERVAL
    if enable_keeper:
        interval_input = input(f"保活间隔（秒）(默认 {KEEP_ALIVE_INTERVAL}): ").strip()
        try:
            keeper_interval = int(interval_input) if interval_input else KEEP_ALIVE_INTERVAL
        except ValueError:
            print(f"[警告] 无效间隔，使用默认值 {KEEP_ALIVE_INTERVAL}")
    
    print("\n" + "=" * 50)
    print("启动Token管理服务...")
    print(f"  地址: http://{host}:{port}")
    print(f"  保活服务: {'启用' if enable_keeper else '禁用'}")
    if enable_keeper:
        print(f"  保活间隔: {keeper_interval}秒")
    print("=" * 50)
    print("\n按 Ctrl+C 停止服务\n")
    
    try:
        await run_server(
            host=host,
            port=port,
            enable_keeper=enable_keeper,
            keeper_interval=keeper_interval
        )
    except KeyboardInterrupt:
        print("\n\n[退出] Token管理服务已停止")
    except Exception as e:
        print(f"\n[错误] 服务异常: {str(e)}")


async def main():
    """主函数"""
    # 支持命令行参数直接执行
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "false_sign":
            date = sys.argv[2] if len(sys.argv) > 2 else None
            await run_false_sign(date)
            return
        elif cmd == "crawler":
            await run_realtime_crawler()
            return
        elif cmd == "token_manager":
            await run_token_manager()
            return
    
    # 交互式菜单
    while True:
        show_menu()
        choice = input("请选择功能: ").strip()
        
        if choice == "1":
            date = get_date_input()
            await run_false_sign(date)
        elif choice == "2":
            await run_realtime_crawler()
        elif choice == "3":
            await run_token_manager()
        elif choice == "0":
            print("再见!")
            break
        else:
            print("[错误] 无效选择，请重新输入")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[退出] 用户中断")
