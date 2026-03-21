package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.lang.reflect.Constructor;
import java.util.Collections;
import java.util.Map;

public class CSVRecord_2_6Test {

    @Test
    @Timeout(8000)
    public void testGetByIndex() throws Exception {
        // Prepare values array
        String[] values = new String[] {"value0", "value1", "value2"};

        // Prepare empty mapping (not used in get(int))
        Map<String, Integer> mapping = Collections.emptyMap();

        // Use reflection to invoke the package-private constructor (4 params)
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance(values, mapping, null, 1L);

        // Test valid indices
        assertEquals("value0", record.get(0));
        assertEquals("value1", record.get(1));
        assertEquals("value2", record.get(2));

        // Test out of bounds index - should throw ArrayIndexOutOfBoundsException
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> record.get(-1));
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> record.get(3));
    }
}