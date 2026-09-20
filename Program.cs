using System;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace RD_GameAuto_FGOA
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            // 전역 예외 처리기 등록 (미처리 예외로 인한 조용한 크래시 방지 및 로그 저장)
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (sender, e) => HandleException("ThreadException", e.Exception);
            AppDomain.CurrentDomain.UnhandledException += (sender, e) => HandleException("UnhandledException", e.ExceptionObject as Exception);

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            
            try
            {
                Application.Run(new MainForm());
            }
            catch (Exception ex)
            {
                HandleException("MainLoopException", ex);
            }
        }

        private static void HandleException(string source, Exception ex)
        {
            if (ex is System.Runtime.InteropServices.ExternalException || (ex?.Message?.Contains("GDI+") == true))
            {
                // .NET 10 WinForms SplitContainer/화면전환 일시적 GDI+ 버그는 무시하여 지속 작동 보장
                return;
            }

            string errMessage = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] [{source}] 오류 발생:\n{ex?.Message}\n\n상세 정보:\n{ex?.StackTrace}";
            try
            {
                File.AppendAllText("fgoa_crash.log", errMessage + "\n" + new string('-', 80) + "\n");
            }
            catch
            {
                // 로그 저장 실패는 무시
            }

            MessageBox.Show(
                $"프로그램 실행 중 오류가 발생했습니다.\n\n오류: {ex?.Message}\n(자세한 내용은 fgoa_crash.log 참조)",
                "FGOA 오류 알림",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
}
