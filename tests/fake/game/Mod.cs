using HarmonyLib;
public class M {
  public void A(TileEntityWorkstation t){ t.read(1); var f = t.fuel; GameManager.Instance.SaveWorld(); new TileEntityWorkstation.Inner().Go(); }
  public void B(ITileEntityLootable l){ }
}
[HarmonyPatch(typeof(TileEntityWorkstation), "readItemStackArray")] public class P1 { }
[HarmonyPatch(typeof(TileEntityWorkstation), "read")] public class P2 { }
