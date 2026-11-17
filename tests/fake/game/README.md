Tiny stand-ins for the game's Assembly-CSharp.dll (two "versions") and a code mod that uses it,
for the mod compatibility check tests. Built with Mono:

    mcs -target:library -out:Assembly-CSharp-3.4.dll Game.cs
    sed -e 's/public interface ITileEntityLootable { }//; s/ public int fuel;//' Game.cs > /tmp/Game2.cs
    mcs -target:library -out:Assembly-CSharp-3.5.dll /tmp/Game2.cs
    mcs -target:library -out:0Harmony.dll Harm.cs      (stand-in for the game's Mods/0_TFP_Harmony/0Harmony.dll)
    mcs -target:library -r:Assembly-CSharp-3.4.dll -r:0Harmony.dll -out:TestCodeMod.dll Mod.cs
