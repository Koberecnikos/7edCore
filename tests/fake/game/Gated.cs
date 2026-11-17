public class GatedLoader : IModApi {
  public void InitMod(Mod m) {
    int minor = 40;
    if (minor != 10 && minor != 30) throw new System.NotSupportedException("This update supports 7D2D 3.1 and 3.3 only.");
    if (minor < 0) throw new System.InvalidOperationException("Duplicate loader detected.");
  }
}
